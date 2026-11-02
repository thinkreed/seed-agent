import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { RecordingChannel } from "../src/channels/recording.ts";
import type { Decision } from "../src/domain.ts";
import { buildPolicy } from "../src/policy.ts";
import { Runtime } from "../src/runtime.ts";
import { RecordingExecutor } from "./fakes.ts";
import * as h from "./helpers.ts";

const replyDecision: Decision = {
  kind: "reply",
  strength: "explicit",
  reason: "status question",
  rules: [],
  scope: "ticket",
  reply: "下一代 agent harness 已经跑通，正在做最后核对。",
};

test("Router 的 reply 决策直接回信道，不创建工单", async () => {
  const clock = new FakeClock();
  const channel = new RecordingChannel();
  const executor = new RecordingExecutor();
  const policy = buildPolicy(
    [{ source: "fs", actor: "*", allow: true, strength: "explicit", note: "feishu" }],
    "auto",
    [["fs", "*"]],
  );
  const rt = Runtime.build({
    assessor: { assess: () => replyDecision },
    executor,
    config: { dbPath: ":memory:", policy, channels: channel },
    clock,
  });
  rt.engine.ingest(
    h.trigger("trg-reply", {
      source: "fs",
      text: "现在下一代 agent 这事情咋样了",
      threadIds: ["fs:oc_demo"],
      channelIds: ["fs:oc_demo"],
    }),
  );
  await rt.tickUntilIdle();
  const state = rt.engine.state;
  assert.equal(Object.keys(state.tickets).length, 0, "reply 不应建工单");
  assert.equal(state.sentMessages.size, 1);
  assert.equal(channel.sent.length, 1);
  assert.equal(channel.sent[0]?.text, replyDecision.reply);
  rt.close();
});