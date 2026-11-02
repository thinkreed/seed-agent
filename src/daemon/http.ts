/**
 * HTTP daemon：把 DaemonAgent 暴露成可跨机器访问的执行环境（文章 §5.2）。
 * 只执行命令/读写文件并回报；不保存会话状态，重启后由计算侧 recover() 重拉。
 */

import { readFileSync } from "node:fs";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { createServer as createHttpsServer, type Server as HttpsServer } from "node:https";

import type { Clock } from "../clock.ts";
import type { DaemonEvent } from "../executor/protocol.ts";
import { DaemonAgent } from "./agent.ts";

export interface HttpDaemonOptions {
  readonly root: string;
  readonly clock: Clock;
  readonly env?: Readonly<Record<string, string>>;
  readonly token?: string;
  readonly host?: string;
  readonly port?: number;
  /** 事件缓冲上限（默认 1000）。 */
  readonly maxEvents?: number;
  /** 直接启用 TLS；生产也可由反向代理终止 TLS。 */
  readonly tls?: { readonly cert: string; readonly key: string };
}

export interface RunningDaemon {
  readonly server: Server | HttpsServer;
  readonly port: number;
  close(): Promise<void>;
}

export async function startHttpDaemon(options: HttpDaemonOptions): Promise<RunningDaemon> {
  const events: { seq: number; event: DaemonEvent }[] = [];
  let seq = 0;
  const maxEvents = options.maxEvents ?? 1000;
  const metrics = { requests: 0, errors: 0, startedAt: options.clock.now() };
  const agent = new DaemonAgent({
    clock: options.clock,
    root: options.root,
    ...(options.env ? { env: options.env } : {}),
    emit: (event) => {
      seq += 1;
      events.push({ seq, event });
      if (events.length > maxEvents) events.shift();
    },
  });
  const token = options.token?.trim();
  const host = options.host ?? "127.0.0.1";
  if (!isLoopback(host) && !token) {
    throw new Error(`daemon requires SA_DAEMON_TOKEN when listening on ${host}`);
  }
  const server = options.tls
    ? createHttpsServer(
        { cert: readFileSync(options.tls.cert), key: readFileSync(options.tls.key) },
        (request, response) => {
          void handle(request, response, agent, events, token, metrics, options.clock);
        },
      )
    : createServer((request, response) => {
        void handle(request, response, agent, events, token, metrics, options.clock);
      });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(options.port ?? 0, host, () => resolve());
  });
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : (options.port ?? 0);
  return {
    server,
    port,
    close: () =>
      new Promise((resolve) => {
        server.close(() => resolve());
        server.closeAllConnections();
      }),
  };
}

function isLoopback(host: string): boolean {
  return host === "127.0.0.1" || host === "::1" || host === "localhost";
}

async function handle(
  request: IncomingMessage,
  response: ServerResponse,
  agent: DaemonAgent,
  events: { seq: number; event: DaemonEvent }[],
  token: string | undefined,
  metrics: { requests: number; errors: number; startedAt: number },
  clock: Clock,
): Promise<void> {
  const url = new URL(request.url ?? "/", "http://daemon");
  metrics.requests += 1;
  if (url.pathname === "/health") return json(response, 200, { ok: true });
  if (token && request.headers.authorization !== `Bearer ${token}`) {
    metrics.errors += 1;
    return json(response, 401, { ok: false, error: "unauthorized" });
  }
  if (url.pathname === "/metrics") {
    const uptime = Math.max(0, clock.now() - metrics.startedAt);
    return text(
      response,
      200,
      [
        "# HELP seed_daemon_requests_total HTTP requests received",
        "# TYPE seed_daemon_requests_total counter",
        `seed_daemon_requests_total ${metrics.requests}`,
        "# TYPE seed_daemon_errors_total counter",
        `seed_daemon_errors_total ${metrics.errors}`,
        "# TYPE seed_daemon_events_buffered gauge",
        `seed_daemon_events_buffered ${events.length}`,
        "# TYPE seed_daemon_uptime_seconds gauge",
        `seed_daemon_uptime_seconds ${uptime}`,
        "",
      ].join("\n"),
    );
  }
  try {
    if (url.pathname === "/request" && request.method === "POST") {
      const body = (await readJson(request)) as Parameters<DaemonAgent["handle"]>[0];
      return json(response, 200, await agent.handle(body));
    }
    if (url.pathname === "/events" && request.method === "GET") {
      const after = Number(url.searchParams.get("after") ?? 0);
      return json(response, 200, { events: events.filter((item) => item.seq > after) });
    }
    metrics.errors += 1;
    return json(response, 404, { ok: false, error: "unknown endpoint" });
  } catch (error) {
    metrics.errors += 1;
    return json(response, 500, { ok: false, error: String(error).slice(0, 400) });
  }
}

function readJson(request: IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    let body = "";
    request.on("data", (chunk: Buffer) => {
      body += chunk.toString("utf8");
      if (body.length > 1_000_000) {
        reject(new Error("body too large"));
        request.destroy();
      }
    });
    request.on("end", () => {
      try {
        resolve(JSON.parse(body || "{}"));
      } catch (error) {
        reject(error);
      }
    });
    request.on("error", reject);
  });
}

function json(response: ServerResponse, status: number, payload: unknown): void {
  const body = JSON.stringify(payload);
  response.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
  });
  response.end(body);
}

function text(response: ServerResponse, status: number, body: string): void {
  response.writeHead(status, {
    "content-type": "text/plain; version=0.0.4; charset=utf-8",
    "content-length": Buffer.byteLength(body),
  });
  response.end(body);
}