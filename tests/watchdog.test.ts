import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { ev } from "../src/builders.ts";
import { RecordingExecutor, ScriptedAssessor } from "../src/fakes.ts";
import type { State } from "../src/domain.ts";
import { Runtime } from "../src/runtime.ts";
import { Watchdog, type WatchdogFinding, type WatchdogVerdict } from "../src/watchdog.ts";
import * as h from "./helpers.ts";

function runtime(slots = 1) {
  const clock = new FakeClock();
  const executor = new RecordingExecutor();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([h.accept()]),
    executor,
    config: { policy: h.policy(), slots },
    clock,
  });
  return { rt, clock };
}

async function runningTicket(): Promise<{ rt: ReturnType<typeof runtime>["rt"]; clock: FakeClock; state: State }> {
  const { rt, clock } = runtime();
  rt.engine.ingest(h.trigger());
  await rt.tickUntilIdle();
  return { rt, clock, state: rt.engine.state };
}

test("没有工单时安静（ok）", async () => {
  const { rt, clock } = runtime();
  const watchdog = new Watchdog({ clock });
  const report = await watchdog.check(rt.engine.state);
  assert.deepEqual(report.findings, []);
  assert.equal(report.verdict.action, "ok");
  rt.close();
});

test("长时间无活动的工单被判定为 stalled", async () => {
  const { rt, clock } = await runningTicket();
  clock.advance(1801);
  const watchdog = new Watchdog({ clock, staleSeconds: 1800 });
  const report = await watchdog.check(rt.engine.state);
  assert.equal(report.findings.length, 1);
  assert.equal(report.findings[0]?.kind, "stalled");
  assert.equal(report.verdict.action, "intervene");
  rt.close();
});

test("刚活动的工单不算停滞", async () => {
  const { rt, clock } = await runningTicket();
  clock.advance(60);
  const watchdog = new Watchdog({ clock, staleSeconds: 1800 });
  const report = await watchdog.check(rt.engine.state);
  assert.equal(report.findings.length, 0);
  rt.close();
});

test("投递失败的输入会被报告为 undelivered", async () => {
  const { rt, clock } = await runningTicket();
  const ticket = Object.values(rt.engine.state.tickets)[0];
  assert.ok(ticket);
  const input = h.input("inp-1", { ticketId: ticket.id, at: clock.now() });
  rt.store.append(ev.inputFannedOut(input, clock.now()));
  rt.store.append(ev.inputUndelivered(input.id, "session down", clock.now()));

  const watchdog = new Watchdog({ clock });
  const report = await watchdog.check(rt.engine.state);
  assert.ok(report.findings.some((finding) => finding.kind === "undelivered"));
  rt.close();
});

test("有判据时交给模型裁定，并把 findings 传过去", async () => {
  const { rt, clock } = await runningTicket();
  clock.advance(3600);
  const seen: WatchdogFinding[][] = [];
  const judge = {
    async judge(findings: readonly WatchdogFinding[]): Promise<WatchdogVerdict> {
      seen.push([...findings]);
      return { action: "intervene", reason: "model-judged" };
    },
  };
  const watchdog = new Watchdog({ clock, staleSeconds: 60, judge });
  const report = await watchdog.check(rt.engine.state);
  assert.equal(seen.length, 1);
  assert.equal(report.verdict.reason, "model-judged");
  rt.close();
});