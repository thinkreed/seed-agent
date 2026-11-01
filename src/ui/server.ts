/**
 * 桌面控制台的本地 HTTP 服务：静态资源 + JSON API + SSE。
 * 只绑定 127.0.0.1；可选 token 校验，默认关闭（本机单用户）。
 */

import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { AddressInfo } from "node:net";

import type { AnyEvent } from "../events.ts";
import type { Runtime } from "../runtime.ts";
import { buildTicketView, buildUiState, eventRow } from "./view.ts";

export interface UiServerOptions {
  readonly runtime: Runtime;
  readonly port?: number;
  readonly host?: string;
  readonly token?: string;
  readonly webDir?: string;
  readonly slots?: number;
  /** SSE 推送间隔（毫秒）。 */
  readonly tickMs?: number;
}

export interface UiServer {
  readonly url: string;
  readonly port: number;
  close(): Promise<void>;
}

const WEB_DIR = new URL("./web", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const STATIC: Record<string, { file: string; type: string }> = {
  "/": { file: "index.html", type: "text/html; charset=utf-8" },
  "/index.html": { file: "index.html", type: "text/html; charset=utf-8" },
  "/app.css": { file: "app.css", type: "text/css; charset=utf-8" },
  "/app.js": { file: "app.js", type: "text/javascript; charset=utf-8" },
  "/favicon.svg": { file: "favicon.svg", type: "image/svg+xml" },
};

export async function createUiServer(options: UiServerOptions): Promise<UiServer> {
  const host = options.host ?? "127.0.0.1";
  const webDir = options.webDir ?? WEB_DIR;
  const token = options.token;
  const server = createServer((request, response) => {
    void handle(request, response).catch((error: unknown) => {
      respondJson(response, 500, { error: String(error) });
    });
  });

  const handle = async (request: IncomingMessage, response: ServerResponse): Promise<void> => {
    const url = new URL(request.url ?? "/", `http://${request.headers.host ?? "localhost"}`);
    if (url.pathname.startsWith("/api/") && token && !authorized(request, url, token)) {
      respondJson(response, 401, { error: "unauthorized" });
      return;
    }
    if (request.method === "GET" && STATIC[url.pathname]) {
      const entry = STATIC[url.pathname] as { file: string; type: string };
      try {
        const body = readFileSync(join(webDir, entry.file));
        response.writeHead(200, { "content-type": entry.type, "cache-control": "no-store" });
        response.end(body);
      } catch {
        respondJson(response, 404, { error: "asset missing" });
      }
      return;
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

  const currentState = () =>
    buildUiState(options.runtime.engine.state, {
      paused: options.runtime.engine.isPaused,
      slots: options.slots ?? options.runtime.config.slots ?? 4,
      lastSeq: options.runtime.store.lastSeq(),
    });

  const recentEvents = (after: number, limit: number) =>
    options.runtime.store.events(after).slice(0, limit).map((event: AnyEvent) => eventRow(event));

  const runCommand = async (body: Record<string, unknown>): Promise<{ ok: boolean; error?: string }> => {
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
        if (!text) return { ok: false, error: "text is required" };
        engine.personMessage(String(body.ticketId ?? ""), text);
        await engine.tick();
        return { ok: true };
      }
      return { ok: false, error: `unknown command: ${type}` };
    } catch (error) {
      return { ok: false, error: String(error) };
    }
  };

  const openStream = (request: IncomingMessage, response: ServerResponse): void => {
    response.writeHead(200, {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-cache, no-transform",
      connection: "keep-alive",
      "x-accel-buffering": "no",
    });
    let lastSeq = -1;
    let lastPaused: boolean | null = null;
    const push = () => {
      const ui = currentState();
      if (ui.lastSeq === lastSeq && ui.paused === lastPaused) return;
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

  await new Promise<void>((resolve) => server.listen(options.port ?? 0, host, () => resolve()));
  const address = server.address() as AddressInfo;
  return {
    url: `http://${host}:${address.port}/`,
    port: address.port,
    close: () =>
      new Promise<void>((resolve) => {
        server.close(() => resolve());
        server.closeAllConnections?.();
      }),
  };
}

function authorized(request: IncomingMessage, url: URL, token: string): boolean {
  const header = request.headers["x-seed-token"];
  return header === token || url.searchParams.get("token") === token;
}

function respondJson(response: ServerResponse, status: number, body: unknown): void {
  if (response.headersSent) return;
  response.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  response.end(JSON.stringify(body));
}

async function readJson(request: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(Buffer.from(chunk));
  if (chunks.length === 0) return {};
  try {
    const parsed: unknown = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}