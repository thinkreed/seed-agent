import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { ev } from "../src/builders.ts";
import { RecordingExecutor, ScriptedAssessor } from "./fakes.ts";
import { SeqIds } from "../src/ids.ts";
import { Runtime } from "../src/runtime.ts";
import * as h from "./helpers.ts";

function build(decisions: Parameters<typeof ScriptedAssessor>[0], slots = 4) {
  const clock = new FakeClock();
  const assessor = new ScriptedAssessor(decisions);
  const executor = new RecordingExecutor();
  const rt = Runtime.build({
    assessor,
    executor,
    config: { dbPath: ":memory:", policy: h.policy(), slots },
    clock,
    ids: new SeqIds(),
  });
  return { rt, clock, assessor, executor };
}

test("端到端：Trigger -> Eval -> Ticket -> Assignment -> Report", async () => {
  const { rt, executor } = build([h.accept()]);
  rt.engine.ingest(h.trigger());
  await rt.tickUntilIdle();

  const state = rt.engine.state;
  const ticket = Object.values(state.tickets)[0];
  assert.ok(ticket);
  assert.equal(ticket.state, "open");
  assert.equal(Object.values(state.assignments)[0]?.state, "running");
  assert.equal(executor.launched.length, 1);

  const assignment = Object.values(state.assignments)[0];
  assert.ok(assignment);
  rt.engine.report(h.report("ready", { assignmentId: assignment.id, ticketId: ticket.id, summary: "done" }));
  assert.equal(Object.values(rt.engine.state.tickets)[0]?.state, "ended");
  assert.equal(executor.stopped.length, 1, "报告结束后应停掉执行器进程");
  rt.close();
});

test("重试：结束 assignment 时同时停掉旧 worker", async () => {
  const { rt, executor } = build([h.accept()]);
  rt.engine.ingest(h.trigger());
  await rt.tickUntilIdle();
  const ticket = Object.values(rt.engine.state.tickets)[0];
  assert.ok(ticket);
  rt.engine.retry(ticket.id);
  assert.equal(executor.stopped.length, 1);
  rt.close();
});

test("幂等：同一个 Trigger 重复 ingest 只入账一次", async () => {
  const { rt } = build([]);
  rt.engine.ingest(h.trigger());
  const first = rt.store.lastSeq();
  assert.deepEqual(rt.engine.ingest(h.trigger()), []);
  assert.equal(rt.store.lastSeq(), first);
  assert.equal(Object.keys(rt.engine.state.triggers).length, 1);
  rt.close();
});

test("批处理：tick 之前到达的多条 Trigger 合并进一次 Eval", async () => {
  const { rt, assessor } = build([h.ignore()]);
  rt.engine.ingest(h.trigger("trg-1"));
  rt.engine.ingest(h.trigger("trg-2"));
  rt.engine.ingest(h.trigger("trg-3"));
  const evals = Object.values(rt.engine.state.evals);
  assert.equal(evals.length, 1);
  assert.deepEqual(evals[0]?.triggerIds, ["trg-1", "trg-2", "trg-3"]);

  await rt.tickUntilIdle();
  assert.equal(assessor.calls.length, 1);
  assert.equal(assessor.calls[0]?.triggers.length, 3);
  rt.close();
});

test("ignore 决定不产生工单", async () => {
  const { rt } = build([h.ignore()]);
  rt.engine.ingest(h.trigger());
  await rt.tickUntilIdle();
  assert.equal(Object.keys(rt.engine.state.tickets).length, 0);
  assert.equal(rt.engine.state.dispositions["trg-1"], "evaluated");
  rt.close();
});

test("订阅直通：同一线程的后续 Trigger 直接投递，不再走 Eval", async () => {
  const { rt, executor, assessor } = build([h.accept()]);
  rt.engine.ingest(h.trigger("trg-1"));
  await rt.tickUntilIdle();
  const evalCount = Object.keys(rt.engine.state.evals).length;

  rt.engine.ingest(h.trigger("trg-2"));
  await rt.tickUntilIdle();

  assert.equal(rt.engine.state.dispositions["trg-2"], "fanned_out");
  assert.equal(executor.delivered.length, 1);
  assert.equal(Object.keys(rt.engine.state.evals).length, evalCount);
  assert.equal(assessor.calls.length, 1);
  rt.close();
});

test("stop 决定结束线程上的工单", async () => {
  const { rt, clock } = build([h.accept(), h.stop()]);
  rt.engine.ingest(h.trigger("trg-1"));
  await rt.tickUntilIdle();
  const ticket = Object.values(rt.engine.state.tickets)[0];
  assert.ok(ticket);

  rt.store.append(ev.subscriptionRemoved(ticket.id, "thr-1", clock.now()));
  rt.engine.ingest(h.trigger("trg-2"));
  await rt.tickUntilIdle();
  assert.equal(Object.values(rt.engine.state.tickets)[0]?.state, "ended");
  rt.close();
});

test("并发槽：slots=1 时同一波只派一个 assignment", async () => {
  const { rt } = build([h.accept(), h.accept()], 1);
  rt.engine.ingest(h.trigger("trg-a", { threadIds: ["thr-a"] }));
  rt.engine.ingest(h.trigger("trg-b", { threadIds: ["thr-b"] }));
  await rt.tickUntilIdle();

  const assignments = Object.values(rt.engine.state.assignments);
  assert.equal(assignments.length, 1);

  const running = assignments[0];
  assert.ok(running);
  rt.engine.report(h.report("ready", { assignmentId: running.id, ticketId: running.ticketId }));
  await rt.tickUntilIdle();
  assert.equal(Object.values(rt.engine.state.assignments).length, 2);
  rt.close();
});

test("人的消息可以 resume 已结束的工单", async () => {
  const { rt } = build([h.accept()]);
  rt.engine.ingest(h.trigger());
  await rt.tickUntilIdle();
  const ticket = Object.values(rt.engine.state.tickets)[0];
  assert.ok(ticket);
  const assignment = Object.values(rt.engine.state.assignments)[0];
  assert.ok(assignment);
  rt.engine.report(h.report("ready", { assignmentId: assignment.id, ticketId: ticket.id }));
  assert.equal(ticket.state, "open");

  rt.engine.personMessage(ticket.id, "还有一处要改");
  await rt.tickUntilIdle();
  assert.equal(Object.values(rt.engine.state.tickets)[0]?.state, "open");
  rt.close();
});

test("失败报告不会结束工单", async () => {
  const { rt } = build([h.accept()]);
  rt.engine.ingest(h.trigger());
  await rt.tickUntilIdle();
  const ticket = Object.values(rt.engine.state.tickets)[0];
  const assignment = Object.values(rt.engine.state.assignments)[0];
  assert.ok(ticket && assignment);
  rt.engine.report(h.report("failed", { assignmentId: assignment.id, ticketId: ticket.id }));
  assert.equal(Object.values(rt.engine.state.tickets)[0]?.state, "open");
  rt.close();
});