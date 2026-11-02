import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { buildPolicy } from "../src/policy.ts";
import { Runtime } from "../src/runtime.ts";
import { RouterSession } from "../src/router_session.ts";
import type { ModelClient, ModelMessage } from "../src/model.ts";
import { RecordingExecutor, ScriptedAssessor } from "./fakes.ts";
import * as h from "./helpers.ts";

class RecordingModel implements ModelClient {
  readonly calls: ModelMessage[][] = [];
  readonly replies: string[];

  constructor(replies: string[]) {
    this.replies = [...replies];
  }

  async complete(messages: readonly ModelMessage[]): Promise<string> {
    this.calls.push([...messages]);
    return this.replies.shift() ?? '{"decisions":[]}';
  }
}

function stateFor(rt: Runtime) {
  return () => rt.engine.state;
}

test("RouterSession：同一 tick 的多个 Thread 合并成一次模型调用", async () => {
  const clock = new FakeClock();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([h.accept()]),
    executor: new RecordingExecutor(),
    config: { dbPath: ":memory:", policy: h.policy() },
    clock,
  });
  const model = new RecordingModel([
    JSON.stringify({
      decisions: ["th-1", "th-2"].map((threadId) => ({
        threadId,
        kind: "accept",
        strength: "explicit",
        scope: "ticket",
        reason: "batch",
        rules: [],
      })),
    }),
  ]);
  const batches: number[] = [];
  const router = new RouterSession({
    client: model,
    state: stateFor(rt),
    onBatch: (batch) => batches.push(batch.threads),
  });
  const policy = buildPolicy([], "auto", []);
  const contexts = ["th-1", "th-2"].map((threadId) => ({
    threadId,
    triggers: [h.trigger(`trg-${threadId}`, { threadIds: [threadId] })],
    tickets: [],
    policy,
  }));
  const decisions = await Promise.all(contexts.map((context) => router.assess(context)));
  assert.equal(model.calls.length, 1);
  assert.deepEqual(batches, [2]);
  assert.deepEqual(decisions.map((decision) => decision.kind), ["accept", "accept"]);
  rt.close();
});

test("RouterSession：recall 会先取下一跳再继续决策", async () => {
  const clock = new FakeClock();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([h.accept()]),
    executor: new RecordingExecutor(),
    config: { dbPath: ":memory:", policy: h.policy() },
    clock,
  });
  rt.engine.ingest(h.trigger("trg-1"));
  await rt.tickUntilIdle();
  const model = new RecordingModel([
    '{"recall":[{"kind":"thread","id":"thr-1"}]}',
    '{"decisions":[{"threadId":"thr-1","kind":"ignore","strength":"inferred","scope":"ticket","reason":"seen","rules":[]}]}',
  ]);
  const router = new RouterSession({ client: model, state: stateFor(rt) });
  const decision = await router.assess({
    threadId: "thr-1",
    triggers: [h.trigger("trg-1")],
    tickets: [],
    policy: rt.engine.state.policy,
  });
  assert.equal(model.calls.length, 2);
  assert.equal(decision.kind, "ignore");
  const secondPrompt = model.calls[1]?.map((message) => message.content).join("\n") ?? "";
  assert.match(secondPrompt, /recallResults/);
  rt.close();
});

test("RouterSession：observe 把直通 Worker 的事件也写进全局记忆", () => {
  const clock = new FakeClock();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([]),
    executor: new RecordingExecutor(),
    config: { dbPath: ":memory:", policy: h.policy() },
    clock,
  });
  const model = new RecordingModel([]);
  const router = new RouterSession({ client: model, state: () => rt.engine.state });
  router.observe(h.trigger("trg-obs", { text: "PR 里改成方案 B", threadIds: ["gh:o/r#pr:1"] }));
  assert.match(router.snapshot().memory, /PR 里改成方案 B/);
  assert.equal(model.calls.length, 0, "观测不应触发模型调用");
  rt.close();
});

test("RouterSession：reply 决策带回复文本且不建工单", async () => {
  const clock = new FakeClock();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([]),
    executor: new RecordingExecutor(),
    config: { dbPath: ":memory:", policy: h.policy() },
    clock,
  });
  const model = new RecordingModel([
    JSON.stringify({
      decisions: [
        {
          threadId: "thr-1",
          kind: "reply",
          strength: "explicit",
          scope: "ticket",
          reason: "status",
          rules: [],
          reply: "已跑通，正在核对。",
        },
      ],
    }),
  ]);
  const router = new RouterSession({ client: model, state: () => rt.engine.state });
  const decision = await router.assess({
    threadId: "thr-1",
    triggers: [h.trigger("trg-1", { text: "进展如何" })],
    tickets: [],
    policy: rt.engine.state.policy,
  });
  assert.equal(decision.kind, "reply");
  assert.equal(decision.reply, "已跑通，正在核对。");
  rt.close();
});

test("RouterSession：chat 保留记忆与对话历史", async () => {
  const clock = new FakeClock();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([h.accept()]),
    executor: new RecordingExecutor(),
    config: { dbPath: ":memory:", policy: h.policy() },
    clock,
  });
  const model = new RecordingModel(['{"reply":"收到，我在。"}']);
  const router = new RouterSession({ client: model, state: stateFor(rt) });
  assert.equal(await router.chat("在吗"), "收到，我在。");
  await router.chat("写个评审结论", "async");
  const asyncPrompt = model.calls.at(-1)?.map((message) => message.content).join("\n") ?? "";
  assert.match(asyncPrompt, /asynchronous/);
  const snapshot = router.snapshot();
  assert.equal(snapshot.history, 4);
  assert.match(snapshot.memory, /在吗/);
  rt.close();
});