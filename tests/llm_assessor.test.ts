import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { LlmAssessor } from "../src/assessor_llm.ts";
import type { ModelMessage } from "../src/model.ts";
import { buildView } from "../src/context.ts";
import type { AssessContext } from "../src/ports.ts";
import * as h from "./helpers.ts";

class ScriptedModel {
  readonly calls: (readonly ModelMessage[])[] = [];
  private readonly replies: string[];

  constructor(replies: string[]) {
    this.replies = [...replies];
  }

  async complete(messages: readonly ModelMessage[]): Promise<string> {
    this.calls.push(messages);
    return this.replies.shift() ?? "{}";
  }
}

function context(): AssessContext {
  return {
    threadId: "thr-1",
    triggers: [h.trigger("trg-1", { text: "请修复登录 500" })],
    tickets: [],
    policy: h.policy(),
  };
}

test("LlmAssessor：组装提示词并解析模型决定", async () => {
  const model = new ScriptedModel([
    '{"kind":"accept","strength":"explicit","reason":"direct request","scope":"ticket"}',
  ]);
  const assessor = new LlmAssessor(model);
  const decision = await assessor.assess(context());

  assert.equal(decision.kind, "accept");
  assert.equal(decision.strength, "explicit");
  assert.equal(model.calls.length, 1);
  const [system, user] = model.calls[0] ?? [];
  assert.match(system?.content ?? "", /Super-agent/);
  assert.match(user?.content ?? "", /trg-1/);
  assert.match(user?.content ?? "", /thr-1/);
});

test("LlmAssessor：模型乱答时降级为 ignore", async () => {
  const assessor = new LlmAssessor(new ScriptedModel(["I cannot help with that."]));
  const decision = await assessor.assess(context());
  assert.equal(decision.kind, "ignore");
  assert.match(decision.reason, /unparsable/);
});

test("buildView：由评估上下文构造视图，策略版本可见", () => {
  const view = buildView(context());
  assert.equal(view.threadId, "thr-1");
  assert.equal(view.triggers[0]?.id, "trg-1");
  assert.equal(view.policyVersion, h.policy().version);
  assert.ok(view.handles.some((handle) => handle.kind === "thread"));
});

test("LlmAssessor 不依赖真实时钟", async () => {
  const clock = new FakeClock();
  const assessor = new LlmAssessor(new ScriptedModel(['{"kind":"ignore"}']));
  await assessor.assess(context());
  assert.equal(clock.now(), 1_700_000_000);
});