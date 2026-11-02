import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { ev } from "../src/builders.ts";
import { Runtime } from "../src/runtime.ts";
import { RecordingExecutor, ScriptedAssessor } from "./fakes.ts";
import * as h from "./helpers.ts";

test("retry 后迟到的 report 不会落到已结束 assignment，也不会结束工单", async () => {
  const clock = new FakeClock();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([h.accept()]),
    executor: new RecordingExecutor(),
    config: { dbPath: ":memory:", policy: h.policy() },
    clock,
  });
  try {
    rt.engine.ingest(h.trigger("trg-1", { threadIds: ["thr-race"], channelIds: ["ch"] }));
    await rt.tickUntilIdle();
    const state = rt.engine.state;
    const ticketId = Object.keys(state.tickets)[0];
    const assignmentId = Object.keys(state.assignments)[0];
    assert.ok(ticketId && assignmentId);

    rt.store.append(ev.assignmentEnded(assignmentId, "retry", 2));
    const produced = rt.engine.report(h.report("ready", { ticketId, assignmentId, at: 3 }));
    assert.equal(produced.length, 0, "late report must be ignored");
    assert.equal(Object.keys(rt.engine.state.reports).length, 0);
    assert.equal(rt.engine.state.tickets[ticketId]?.state, "open");
  } finally {
    rt.close();
  }
});