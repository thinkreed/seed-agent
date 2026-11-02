import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { WatchdogController } from "../src/control.ts";
import { buildPolicy } from "../src/policy.ts";
import { Runtime } from "../src/runtime.ts";
import { Watchdog } from "../src/watchdog.ts";
import { RecordingExecutor, ScriptedAssessor } from "./fakes.ts";
import * as h from "./helpers.ts";

function build(policy = h.policy()) {
  const clock = new FakeClock();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([h.accept()]),
    executor: new RecordingExecutor(),
    config: { dbPath: ":memory:", policy },
    clock,
  });
  return { rt, clock };
}

test("已订阅 Thread 的后续事件仍要过程序层 Gate（不被直通绕过）", async () => {
  const strict = buildPolicy(
    [{ source: "local", actor: "*", allow: true, strength: "explicit", note: "test" }],
    "auto",
    [["local", "alice"]],
  );
  const { rt } = build(strict);
  rt.engine.ingest(h.trigger("trg-1"));
  await rt.tickUntilIdle();
  const ticket = Object.values(rt.engine.state.tickets)[0];
  assert.ok(ticket, "首条 Trigger 应建立工单与订阅");

  rt.engine.ingest(h.trigger("trg-2", { actor: "intruder", text: "noise" }));
  const state = rt.engine.state;
  assert.equal(state.dispositions["trg-2"], "filtered");
  assert.ok(
    !Object.values(state.inputs).some((input) => input.ref === "trg-2"),
    "被过滤的事件不应直通 Worker",
  );
  rt.close();
});

test("在线改策略：policy.changed 后 Gate 立即使用新规则", async () => {
  const { rt } = build();
  const gh = { source: "gh", actor: "bot", threadIds: ["gh:1"], channelIds: ["gh:1"] };
  rt.engine.ingest(h.trigger("trg-gh-1", gh));
  assert.equal(rt.engine.state.dispositions["trg-gh-1"], "filtered");

  const next = buildPolicy(
    [
      { source: "local", actor: "*", allow: true, strength: "explicit", note: "test" },
      { source: "gh", actor: "*", allow: true, strength: "explicit", note: "online" },
    ],
    "auto",
    [["local", "*"], ["gh", "*"]],
  );
  const events = rt.engine.setPolicy(next);
  assert.equal(events.at(-1)?.type, "policy.changed");

  rt.engine.ingest(h.trigger("trg-gh-2", gh));
  assert.notEqual(rt.engine.state.dispositions["trg-gh-2"], "filtered");
  rt.close();
});

test("WatchdogController.applyPolicy 复用引擎唯一写入口", async () => {
  const { rt } = build();
  const controller = new WatchdogController(rt.engine);
  const next = buildPolicy([], "record", []);
  const events = controller.applyPolicy(next);
  assert.equal(events.at(-1)?.type, "policy.changed");
  assert.equal(rt.engine.state.policy?.version, next.version);
  rt.close();
});

test("Watchdog.ask 无模型时给出确定性运维摘要", async () => {
  const { rt, clock } = build();
  rt.engine.ingest(h.trigger());
  await rt.tickUntilIdle();
  clock.advance(60);
  const watchdog = new Watchdog({ clock, staleSeconds: 10 });
  const answer = await watchdog.ask("为什么这个工单没动静？", rt.engine.state);
  assert.match(answer, /为什么这个工单没动静/);
  assert.match(answer, /open 工单 1 个/);
  assert.match(answer, /stalled/);
  rt.close();
});

test("Watchdog.ask 接模型顾问时原样返回顾问回答", async () => {
  const { rt, clock } = build();
  const watchdog = new Watchdog({
    clock,
    advisor: { answer: async (question) => `advisor:${question}` },
  });
  assert.equal(await watchdog.ask("卡在哪", rt.engine.state), "advisor:卡在哪");
  rt.close();
});