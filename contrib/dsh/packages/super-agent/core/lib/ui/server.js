/**
 * 桌面控制台的本地 HTTP 服务：静态资源 + JSON API + SSE。
 * 只绑定 127.0.0.1；可选 token 校验，默认关闭（本机单用户）。
 */
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { buildTicketView, buildUiState, eventRow } from "./view.js";
const WEB_DIR = new URL("./web", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const STATIC = {
    "/": { file: "index.html", type: "text/html; charset=utf-8" },
    "/index.html": { file: "index.html", type: "text/html; charset=utf-8" },
    "/app.css": { file: "app.css", type: "text/css; charset=utf-8" },
    "/app.js": { file: "app.js", type: "text/javascript; charset=utf-8" },
    "/favicon.svg": { file: "favicon.svg", type: "image/svg+xml" },
};
export async function createUiServer(options) {
    const host = options.host ?? "127.0.0.1";
    const webDir = options.webDir ?? WEB_DIR;
    const token = options.token;
    const server = createServer((request, response) => {
        void handle(request, response).catch((error) => {
            respondJson(response, 500, { error: String(error) });
        });
    });
    const handle = async (request, response) => {
        const url = new URL(request.url ?? "/", `http://${request.headers.host ?? "localhost"}`);
        if (url.pathname.startsWith("/api/") && token && !authorized(request, url, token)) {
            respondJson(response, 401, { error: "unauthorized" });
            return;
        }
        if (request.method === "GET") {
            const entry = staticEntry(url.pathname);
            if (entry) {
                try {
                    const body = readFileSync(join(webDir, entry.file));
                    response.writeHead(200, { "content-type": entry.type, "cache-control": "no-store" });
                    response.end(body);
                }
                catch {
                    respondJson(response, 404, { error: "asset missing" });
                }
                return;
            }
        }
        if (url.pathname === "/api/state") {
            respondJson(response, 200, currentState());
            return;
        }
        if (url.pathname === "/api/events") {
            const after = Number(url.searchParams.get("after") ?? 0) || 0;
            const limit = Math.min(500, Number(url.searchParams.get("limit") ?? 200) || 200);
            respondJson(response, 200, recentEvents(after, limit));
            return;
        }
        if (url.pathname.startsWith("/api/tickets/")) {
            const ticketId = decodeURIComponent(url.pathname.slice("/api/tickets/".length));
            const view = buildTicketView(options.runtime.engine.state, ticketId);
            respondJson(response, view ? 200 : 404, view ?? { error: "unknown ticket" });
            return;
        }
        if (url.pathname === "/api/stream" && request.method === "GET") {
            openStream(request, response);
            return;
        }
        if (url.pathname === "/api/command" && request.method === "POST") {
            const body = await readJson(request);
            const result = await runCommand(body);
            respondJson(response, result.ok ? 200 : 400, result);
            return;
        }
        respondJson(response, 404, { error: "not found" });
    };
    const currentState = () => buildUiState(options.runtime.engine.state, {
        paused: options.runtime.engine.isPaused,
        slots: options.slots ?? options.runtime.config.slots ?? 4,
        lastSeq: options.runtime.store.lastSeq(),
    });
    const recentEvents = (after, limit) => options.runtime.store.events(after).slice(0, limit).map((event) => eventRow(event));
    const runCommand = async (body) => {
        const type = String(body.type ?? "");
        const engine = options.runtime.engine;
        try {
            if (type === "pause") {
                engine.pause();
                return { ok: true };
            }
            if (type === "resume") {
                engine.resume();
                return { ok: true };
            }
            if (type === "retry") {
                engine.retry(String(body.ticketId ?? ""));
                await engine.tick();
                return { ok: true };
            }
            if (type === "reply") {
                const text = String(body.text ?? "").trim();
                if (!text)
                    return { ok: false, error: "text is required" };
                engine.personMessage(String(body.ticketId ?? ""), text);
                await engine.tick();
                return { ok: true };
            }
            return { ok: false, error: `unknown command: ${type}` };
        }
        catch (error) {
            return { ok: false, error: String(error) };
        }
    };
    const openStream = (request, response) => {
        response.writeHead(200, {
            "content-type": "text/event-stream; charset=utf-8",
            "cache-control": "no-cache, no-transform",
            connection: "keep-alive",
            "x-accel-buffering": "no",
        });
        let lastSeq = -1;
        let lastPaused = null;
        const push = () => {
            const ui = currentState();
            if (ui.lastSeq === lastSeq && ui.paused === lastPaused)
                return;
            lastSeq = ui.lastSeq;
            lastPaused = ui.paused;
            response.write(`data: ${JSON.stringify(ui)}\n\n`);
        };
        push();
        const timer = setInterval(push, options.tickMs ?? 400);
        const heartbeat = setInterval(() => response.write(": ping\n\n"), 15_000);
        const close = () => {
            clearInterval(timer);
            clearInterval(heartbeat);
            response.end();
        };
        request.on("close", close);
        response.on("error", close);
    };
    await new Promise((resolve) => server.listen(options.port ?? 0, host, () => resolve()));
    const address = server.address();
    return {
        url: `http://${host}:${address.port}/`,
        port: address.port,
        close: () => new Promise((resolve) => {
            server.close(() => resolve());
            server.closeAllConnections?.();
        }),
    };
}
function authorized(request, url, token) {
    const header = request.headers["x-seed-token"];
    return header === token || url.searchParams.get("token") === token;
}
/** 静态资源白名单：内置页面 + vendor/ 下的设计令牌 CSS。 */
function staticEntry(pathname) {
    const direct = STATIC[pathname];
    if (direct)
        return direct;
    const vendor = /^\/vendor\/([A-Za-z0-9._-]+\.css)$/.exec(pathname);
    if (vendor)
        return { file: `vendor/${vendor[1]}`, type: "text/css; charset=utf-8" };
    return null;
}
function respondJson(response, status, body) {
    if (response.headersSent)
        return;
    response.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
    response.end(JSON.stringify(body));
}
async function readJson(request) {
    const chunks = [];
    for await (const chunk of request)
        chunks.push(Buffer.from(chunk));
    if (chunks.length === 0)
        return {};
    try {
        const parsed = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
    }
    catch {
        return {};
    }
}
//# sourceMappingURL=server.js.map