/**
 * daemon 进程入口：只做执行，不持有会话状态。
 *
 *   node src/daemon/main.ts
 *
 * 环境变量：
 *   SEED_DAEMON_ROOT  执行根目录（每个工单一个子目录）
 *   SEED_DAEMON_ENV   额外环境变量（JSON 对象，透传给 worker）
 */

import { createInterface } from "node:readline";

import { SystemClock } from "../clock.ts";
import type { DaemonRequest } from "../executor/protocol.ts";
import { DaemonAgent } from "./agent.ts";

function parseEnv(raw: string | undefined): Record<string, string> {
  if (!raw) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return Object.fromEntries(
        Object.entries(parsed as Record<string, unknown>).map(([key, value]) => [key, String(value)]),
      );
    }
  } catch {
    return {};
  }
  return {};
}

process.on("uncaughtException", (error) => {
  process.stderr.write(`daemon uncaught: ${String(error?.stack ?? error)}\n`);
});
process.on("unhandledRejection", (reason) => {
  process.stderr.write(`daemon unhandled rejection: ${String(reason)}\n`);
});

const agent = new DaemonAgent({
  clock: new SystemClock(),
  root: process.env.SEED_DAEMON_ROOT ?? ".",
  env: parseEnv(process.env.SEED_DAEMON_ENV),
  emit: (event) => process.stdout.write(`${JSON.stringify(event)}\n`),
});

createInterface({ input: process.stdin }).on("line", (line) => {
  const raw = line.trim();
  if (!raw) return;
  void (async () => {
    let request: DaemonRequest;
    try {
      request = JSON.parse(raw) as DaemonRequest;
    } catch {
      return;
    }
    const response = await agent.handle(request);
    process.stdout.write(`${JSON.stringify(response)}\n`);
  })();
});