import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { RecordingChannel } from "../src/channels/recording.ts";
import { Runtime } from "../src/runtime.ts";
import { RecordingExecutor, ScriptedAssessor } from "./fakes.ts";
import * as h from "./helpers.ts";

test("重复的人消息被 ignore 时回上一张工单的结论，而不是静默", async () => {
  const clock = new FakeClock();
  const channel = new RecordingChannel();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([h.accept(), h.ignore("duplicate")]),
    executor: new RecordingExecutor(),
    config: { policy: h.policy(), channels: channel },
    clock,
  });
  try {
    const first = h.trigger("trg-1", { text: "评估当前落地情况", channelIds: ["fs:oc_1"] });
    rt.engine.ingest(first);
    await rt.tickUntilIdle();
    const ticket = Object.values(rt.engine.state.tickets)[0];
    const assignment = Object.values(rt.engine.state.assignments)[0];
    assert.ok(ticket && assignment);
    rt.engine.report(h.report("ready", { ticketId: ticket.id, assignmentId: assignment.id, summary: "已落地" }));
    await rt.tickUntilIdle();

    const second = h.trigger("trg-2", { text: "评估当前落地情况", channelIds: ["fs:oc_1"] });
    rt.engine.ingest(second);
    await rt.tickUntilIdle();
    const last = channel.sent.at(-1)?.text ?? "";
    assert.match(last, /这个请求已经处理过/);
    assert.match(last, /已落地/);
  } finally {
    rt.close();
  }
});