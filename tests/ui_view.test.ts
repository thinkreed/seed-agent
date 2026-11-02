import assert from "node:assert/strict";
import { test } from "node:test";

import type { Decision } from "../src/domain.ts";
import { FakeClock } from "../src/clock.ts";
import { Runtime } from "../src/runtime.ts";
import { buildTicketView, buildUiState, eventRow } from "../src/ui/view.ts";
import { RecordingExecutor, ScriptedAssessor } from "./fakes.ts";
import * as h from "./helpers.ts";

function build(decisions: Decision[]) {
  const clock = new FakeClock();
  const executor = new RecordingExecutor();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor(decisions),
    executor,
    config: { policy: h.policy(), slots: 2 },
    clock,
  });
  return { rt, clock, executor };
}

test("buildUiState：工单、阶段、来源与计数", async () => {
  const { rt } = build([h.accept()]);
  rt.engine.ingest(h.trigger("trg-1", { text: "帮我在目录里写 hello.txt" }));
  await rt.tickUntilIdle();

  const ui = buildUiState(rt.engine.state, { paused: false, slots: 2, lastSeq: rt.store.lastSeq() });
  assert.equal(ui.tickets.length, 1);
  assert.equal(ui.counts.open, 1);
  assert.equal(ui.counts.ended, 0);
  const ticket = ui.tickets[0];
  assert.ok(ticket);
  assert.equal(ticket.source, "local");
  assert.match(ticket.title, /hello\.txt/);
  assert.equal(ticket.state, "open");
  rt.close();
});

test("buildUiState：ready 报告后工单结束", async () => {
  const { rt } = build([h.accept()]);
  rt.engine.ingest(h.trigger());
  await rt.tickUntilIdle();
  const ticket = Object.values(rt.engine.state.tickets)[0];
  const assignment = Object.values(rt.engine.state.assignments)[0];
  assert.ok(ticket && assignment);
  rt.engine.report(h.report("ready", { ticketId: ticket.id, assignmentId: assignment.id, summary: "done" }));

  const ui = buildUiState(rt.engine.state, { paused: false, slots: 2, lastSeq: 0 });
  assert.equal(ui.counts.ended, 1);
  assert.equal(ui.counts.open, 0);
  rt.close();
});

test("buildTicketView：时间线按时间排序并带授权信息", async () => {
  const { rt, clock } = build([h.accept()]);
  rt.engine.ingest(h.trigger("trg-1", { text: "写文件", actor: "alice" }));
  await rt.tickUntilIdle();
  const ticket = Object.values(rt.engine.state.tickets)[0];
  const assignment = Object.values(rt.engine.state.assignments)[0];
  assert.ok(ticket && assignment);
  rt.engine.report(
    h.report("ready", { ticketId: ticket.id, assignmentId: assignment.id, summary: "ok", at: clock.now() + 1 }),
  );

  const view = buildTicketView(rt.engine.state, ticket.id);
  assert.ok(view);
  assert.equal(view.mandate.source, "local");
  assert.equal(view.mandate.scope, "ticket");
  const kinds = view.timeline.map((item) => item.kind);
  assert.equal(kinds[0], "trigger");
  assert.ok(kinds.includes("report"));
  assert.equal(view.timeline.at(-1)?.status, "ready");
  assert.equal(buildTicketView(rt.engine.state, "nope"), null);
  rt.close();
});

test("eventRow：只暴露序号/类型/时间", () => {
  assert.deepEqual(eventRow({ seq: 7, type: "report.recorded", at: 12, data: {} } as never), {
    seq: 7,
    type: "report.recorded",
    at: 12,
  });
});