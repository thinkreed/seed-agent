import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { emptyState } from "../src/domain.ts";
import type { ModelClient, ModelMessage } from "../src/model.ts";
import { RouterSession } from "../src/router_session.ts";

class RecordingModel implements ModelClient {
  readonly calls: ModelMessage[][] = [];
  async complete(messages: readonly ModelMessage[]): Promise<string> {
    this.calls.push([...messages]);
    return JSON.stringify({ reply: "ok" });
  }
}

test("Router 对话历史跨实例恢复，重启后仍有上下文", async () => {
  const dir = mkdtempSync(join(tmpdir(), "seed-router-history-"));
  const path = join(dir, "router-chat.json");
  try {
    const first = new RouterSession({
      client: new RecordingModel(),
      state: () => emptyState(),
      historyPath: path,
    });
    await first.chat("我叫小明");

    const second = new RecordingModel();
    const restarted = new RouterSession({
      client: second,
      state: () => emptyState(),
      historyPath: path,
    });
    await restarted.chat("我叫什么？");
    const prompt = second.calls[0]?.map((message) => message.content).join("\n") ?? "";
    assert.match(prompt, /我叫小明/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});