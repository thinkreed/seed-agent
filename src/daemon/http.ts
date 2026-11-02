/**
 * HTTP daemon：把 DaemonAgent 暴露成可跨机器访问的执行环境（文章 §5.2）。
 * 只执行命令/读写文件并回报；不保存会话状态，重启后由计算侧 recover() 重拉。
 */

import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";

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
}

export interface RunningDaemon {
  readonly server: Server;
  readonly port: number;
  close(): Promise<void>;
}

export async function startHttpDaemon(options: HttpDaemonOptions): Promise<RunningDaemon> {
  const events: { seq: number; event: DaemonEvent }[] = [];
  let seq = 0;
  const maxEvents = options.maxEvents ?? 1000;
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
  const server = createServer((request, response) => {
    void handle(request, response, agent, events, token);
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
): Promise<void> {
  const url = new URL(request.url ?? "/", "http://daemon");
  if (url.pathname === "/health") return json(response, 200, { ok: true });
  if (token && request.headers.authorization !== `Bearer ${token}`) {
    return json(response, 401, { ok: false, error: "unauthorized" });
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
    return json(response, 404, { ok: false, error: "unknown endpoint" });
  } catch (error) {
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