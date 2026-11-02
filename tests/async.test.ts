import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import type { Assignment, Decision, Input, Ticket } from "../src/domain.ts";
import type { Assessor, AssessContext, Executor } from "../src/ports.ts";
import { Runtime } from "../src/runtime.ts";
import * as h from "./helpers.ts";

/** 模拟真实 LLM 的异步评估器。 */
class AsyncAssessor implements Assessor {
  async assess(_context: AssessContext): Promise<Decision> {
    await Promise.resolve();
    return h.accept("async");
  }
}

/** 模拟启动有延迟的执行器。 */
class AsyncExecutor implements Executor {
  readonly launched: string[] = [];

  async launch(assignment: Assignment): Promise<void> {
    await Promise.resolve();
    this.launched.push(assignment.id);
  }

  async deliver(): Promise<void> {
    await Promise.resolve();
  }

  async stop(): Promise<void> {
    await Promise.resolve();
  }
}

test("异步端口：async assessor + async executor 全链路可跑", async () => {
  const clock = new FakeClock();
  const executor = new AsyncExecutor();
  const rt = Runtime.build({
    assessor: new AsyncAssessor(),
    executor,
    config: { policy: h.policy(), slots: 1 },
    clock,
  });

  rt.engine.ingest(h.trigger());
  await rt.tickUntilIdle();

  const ticket = Object.values(rt.engine.state.tickets)[0];
  assert.ok(ticket);
  assert.equal(Object.values(rt.engine.state.assignments)[0]?.state, "running");
  assert.deepEqual(executor.launched, ["as-000001"]);

  const assignment = Object.values(rt.engine.state.assignments)[0];
  assert.ok(assignment);
  rt.engine.report(h.report("ready", { assignmentId: assignment.id, ticketId: ticket.id }));
  assert.equal(Object.values(rt.engine.state.tickets)[0]?.state, "ended");
  rt.close();
});

test("异步执行器抛错：effect 进入退避而不是崩溃", async () => {
  let failures = 0;
  const flaky: Executor = {
    launch: async () => {
      failures += 1;
      throw new Error("worker refused");
    },
    deliver: async () => undefined,
    stop: async () => undefined,
  };
  const clock = new FakeClock();
  const rt = Runtime.build({
    assessor: { assess: () => h.accept() },
    executor: flaky,
    config: { policy: h.policy(), slots: 1 },
    clock,
  });
  rt.engine.ingest(h.trigger());
  await rt.tickUntilIdle();

  assert.equal(failures, 1);
  const ticket = Object.values(rt.engine.state.tickets)[0];
  assert.ok(ticket);
  assert.equal(Object.values(rt.engine.state.assignments)[0]?.state, "pending");
  rt.close();
});

test("Input/Ticket 类型在异步路径上保持不变", async () => {
  const seen: Input[] = [];
  const executor: Executor = {
    launch: async () => undefined,
    deliver: async (_ticket: Ticket, input: Input) => {
      seen.push(input);
    },
    stop: async () => undefined,
  };
  const clock = new FakeClock();
  const rt = Runtime.build({
    assessor: { assess: () => h.accept() },
    executor,
    config: { policy: h.policy(), slots: 1 },
    clock,
  });
  rt.engine.ingest(h.trigger());
  await rt.tickUntilIdle();
  const ticket = Object.values(rt.engine.state.tickets)[0];
  assert.ok(ticket);
  rt.engine.personMessage(ticket.id, "补充一点");
  await rt.tickUntilIdle();
  assert.equal(seen.length, 1);
  assert.equal(seen[0]?.ticketId, ticket.id);
  rt.close();
});