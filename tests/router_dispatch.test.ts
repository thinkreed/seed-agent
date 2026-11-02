import assert from "node:assert/strict";
import { test } from "node:test";

import { emptyState } from "../src/domain.ts";
import type { ModelClient, ModelMessage } from "../src/model.ts";
import { RouterSession } from "../src/router_session.ts";

class WorkModel implements ModelClient {
  async complete(_messages: readonly ModelMessage[]): Promise<string> {
    return JSON.stringify({ reply: "我开一张进展查询单。", work: "检查 superagent 项目当前进展并回报" });
  }
}

test("Router 对话可以携带 work，由调用方升级为工单", async () => {
  const router = new RouterSession({ client: new WorkModel(), state: () => emptyState() });
  const result = await router.chatResult("看看项目进展");
  assert.equal(result.reply, "我开一张进展查询单。");
  assert.equal(result.work, "检查 superagent 项目当前进展并回报");
  // 兼容旧调用：chat() 仍只返回文本。
  assert.equal(await router.chat("再看一次"), "我开一张进展查询单。");
});