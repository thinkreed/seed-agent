/** JSONL 收件箱 Source：每行一个 Trigger，文件追加即产生事件（本地/CI 验证用）。 */

import { existsSync, readFileSync } from "node:fs";

import type { Trigger } from "../domain.ts";
import type { Source } from "../ports.ts";

export class JsonlInboxSource implements Source {
  readonly name = "local";
  private readonly path: string;

  constructor(path: string) {
    this.path = path;
  }

  async poll(): Promise<Trigger[]> {
    if (!existsSync(this.path)) return [];
    const lines = readFileSync(this.path, "utf8").split(/\r?\n/).filter((line) => line.trim());
    const triggers: Trigger[] = [];
    lines.forEach((line, index) => {
      try {
        const parsed = JSON.parse(line) as Partial<Trigger>;
        if (!parsed.text) return;
        triggers.push({
          id: String(parsed.id ?? `jsonl:${index + 1}`),
          source: String(parsed.source ?? "local"),
          actor: String(parsed.actor ?? "operator"),
          text: String(parsed.text),
          threadIds: Array.isArray(parsed.threadIds) ? parsed.threadIds.map(String) : [`local:${index + 1}`],
          channelIds: Array.isArray(parsed.channelIds) ? parsed.channelIds.map(String) : [`local:${index + 1}`],
          at: Number(parsed.at ?? 0),
        });
      } catch {
        // 坏行跳过，不阻塞其余事件
      }
    });
    return triggers;
  }
}