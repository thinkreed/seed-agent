/** Worker 通过控制文件交回 Router / 退订；App 在每轮结束后统一应用。 */

import { readdirSync, readFileSync, unlinkSync } from "node:fs";
import { join } from "node:path";

import type { Engine } from "./engine.ts";

export function drainWorkerControls(engine: Engine, dir: string): number {
  let applied = 0;
  let files: string[];
  try {
    files = readdirSync(dir).filter((file) => file.endsWith(".json"));
  } catch {
    return 0;
  }
  for (const file of files) {
    const path = join(dir, file);
    try {
      const request = JSON.parse(readFileSync(path, "utf8")) as {
        action?: string;
        ticketId?: string;
        threadId?: string;
        reason?: string;
      };
      if (!request.ticketId) continue;
      if (request.action === "handback") engine.handback(request.ticketId, request.reason ?? "");
      else if (request.action === "unsubscribe") engine.unsubscribe(request.ticketId, request.threadId);
      else continue;
      applied += 1;
    } catch {
      // 损坏的控制请求不影响主循环；下一次 tick 继续处理其它请求。
    } finally {
      try {
        unlinkSync(path);
      } catch {
        // already removed
      }
    }
  }
  return applied;
}