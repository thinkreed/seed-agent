import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { ev } from "../src/builders.ts";
import { Runtime } from "../src/runtime.ts";
import { RecordingExecutor, ScriptedAssessor } from "./fakes.ts";
import * as h from "./helpers.ts";

test("工单结束后释放 Thread 订阅，后续消息会开新工单", async () => {
  const clock = new FakeClock();
  const executor = new RecordingExecutor();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([h.accept(), h.accept()]),
    executor,
    config: { dbPath: ":memory:", policy: h.policy() },
    clock,
  });
  try {
    rt.engine.ingest(h.trigger("trg-1", { threadIds: ["thr-reuse"], channelIds: ["ch"] }));
    await rt.tickUntilIdle();
    const first = Object.keys(rt.engine.state.tickets)[0];
    assert.ok(first);
    assert.equal(rt.engine.state.subscriptions.length, 1);

    rt.store.append(ev.ticketEnded(first, "done", "test", 2));
    assert.equal(rt.engine.state.subscriptions.length, 0, "ended ticket must unsubscribe");

    rt.engine.ingest(h.trigger("trg-2", { threadIds: ["thr-reuse"], channelIds: ["ch"], at: 3 }));
    await rt.tickUntilIdle();
    assert.equal(Object.keys(rt.engine.state.tickets).length, 2, "new message opens a new ticket");
  } finally {
    rt.close();
  }
});