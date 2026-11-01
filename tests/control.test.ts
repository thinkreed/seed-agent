import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { RecordingExecutor, ScriptedAssessor } from "../src/fakes.ts";
import { Runtime } from "../src/runtime.ts";
import * as h from "./helpers.ts";

function setup() {
  const clock = new FakeClock();
  const executor = new RecordingExecutor();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([h.accept()]),
    executor,
    config: { policy: h.policy(), slots: 1 },
    clock,
  });
  return { rt, clock, executor };
}

test("pause：暂停期间不评估、不派工；resume 后继续", async () => {
  const { rt } = setup();
  rt.engine.ingest(h.trigger());
  rt.engine.pause();
  await rt.tickUntilIdle();
  assert.equal(Object.keys(rt.engine.state.tickets).length, 0);
  assert.ok(rt.engine.isPaused);

  rt.engine.resume();
  await rt.tickUntilIdle();
  assert.equal(Object.keys(rt.engine.state.tickets).length, 1);
  rt.close();
});

test("Source 在暂停期间仍可记录事件", () => {
  const { rt } = setup();
  rt.engine.pause();
  rt.engine.ingest(h.trigger());
  assert.equal(Object.keys(rt.engine.state.triggers).length, 1);
  rt.close();
});

test("retry：结束当前 assignment 并重新派工", async () => {
  const { rt, executor } = setup();
  rt.engine.ingest(h.trigger());
  await rt.tickUntilIdle();
  const ticket = Object.values(rt.engine.state.tickets)[0];
  assert.ok(ticket);
  assert.equal(executor.launched.length, 1);

  rt.engine.retry(ticket.id);
  await rt.tickUntilIdle();
  assert.equal(executor.launched.length, 2);
  assert.equal(Object.values(rt.engine.state.assignments).length, 2);
  rt.close();
});

test("recoverAfterRestart：running assignment 收口并留下恢复注记", async () => {
  const { rt } = setup();
  rt.engine.ingest(h.trigger());
  await rt.tickUntilIdle();
  const running = Object.values(rt.engine.state.assignments)[0];
  assert.equal(running?.state, "running");

  rt.engine.recoverAfterRestart();
  const afterRecover = rt.engine.state;
  assert.equal(Object.values(afterRecover.assignments)[0]?.state, "ended");
  assert.ok(Object.values(afterRecover.inputs).some((input) => input.kind === "resume"));
  rt.close();
});

test("未知工单的 retry 抛错", () => {
  const { rt } = setup();
  assert.throws(() => rt.engine.retry("tk-ghost"), /unknown ticket/);
  rt.close();
});