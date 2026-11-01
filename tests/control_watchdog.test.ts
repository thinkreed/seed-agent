import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { ev } from "../src/builders.ts";
import { WatchdogController } from "../src/control.ts";
import { RecordingExecutor, ScriptedAssessor } from "../src/fakes.ts";
import { Runtime } from "../src/runtime.ts";
import type { WatchdogFinding } from "../src/watchdog.ts";
import * as h from "./helpers.ts";

function setup() {
  const clock = new FakeClock();
  const executor = new RecordingExecutor();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([h.accept()]),
    executor,
    config: { policy: h.policy(), slots: 2 },
    clock,
  });
  return { rt, clock, executor };
}

async function runningTicket() {
  const ctx = setup();
  ctx.rt.engine.ingest(h.trigger());
  await ctx.rt.tickUntilIdle();
  const ticket = Object.values(ctx.rt.engine.state.tickets)[0];
  assert.ok(ticket);
  return { ...ctx, ticket };
}

test("verdict=ok 时不动作", async () => {
  const { rt } = setup();
  const controller = new WatchdogController(rt.engine);
  const outcome = controller.apply({ findings: [], verdict: { action: "ok", reason: "quiet" } });
  assert.deepEqual(outcome.applied, []);
  rt.close();
});

test("stalled 工单：控制器触发 retry，工单重新派工", async () => {
  const { rt, executor, ticket } = await runningTicket();
  const controller = new WatchdogController(rt.engine);
  const finding: WatchdogFinding = { kind: "stalled", ticketId: ticket.id, detail: "no activity" };
  const outcome = controller.apply({ findings: [finding], verdict: { action: "intervene", reason: "stalled" } });

  assert.deepEqual(outcome.applied, [{ ticketId: ticket.id, kind: "stalled", action: "retry" }]);
  await rt.tickUntilIdle();
  assert.equal(executor.launched.length, 2);
  rt.close();
});

test("undelivered 输入：控制器触发 retry 并重投", async () => {
  const { rt, clock, ticket } = await runningTicket();
  const input = h.input("inp-9", { ticketId: ticket.id, at: clock.now() });
  rt.store.append(ev.inputFannedOut(input, clock.now()));
  rt.store.append(ev.inputUndelivered(input.id, "daemon offline", clock.now()));

  const controller = new WatchdogController(rt.engine);
  const outcome = controller.apply({
    findings: [{ kind: "undelivered", ticketId: ticket.id, detail: "down" }],
    verdict: { action: "intervene", reason: "delivery failed" },
  });
  assert.equal(outcome.applied[0]?.action, "retry");

  await rt.tickUntilIdle();
  assert.ok(Object.values(rt.engine.state.inputs).some((item) => item.kind === "retry"));
  rt.close();
});

test("同一工单的多个 finding 只动作一次", async () => {
  const { rt, ticket } = await runningTicket();
  const controller = new WatchdogController(rt.engine);
  const outcome = controller.apply({
    findings: [
      { kind: "stalled", ticketId: ticket.id, detail: "a" },
      { kind: "undelivered", ticketId: ticket.id, detail: "b" },
    ],
    verdict: { action: "intervene", reason: "both" },
  });
  assert.equal(outcome.applied.length, 1);
  rt.close();
});