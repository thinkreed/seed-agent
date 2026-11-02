import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { ev } from "../src/builders.ts";
import { Runtime } from "../src/runtime.ts";
import { RecordingExecutor, ScriptedAssessor } from "./fakes.ts";
import * as h from "./helpers.ts";

function build() {
  const clock = new FakeClock();
  const executor = new RecordingExecutor();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([h.accept()]),
    executor,
    config: { dbPath: ":memory:", policy: h.policy() },
    clock,
  });
  return { rt, executor };
}

test("Correlation：一条 Trigger 属于多个 Thread 时工单订阅全部线程", async () => {
  const { rt } = build();
  rt.engine.ingest(
    h.trigger("trg-1", {
      threadIds: ["im:group:1", "github:o/r#pr:1"],
      channelIds: ["im:group:1", "github:o/r#pr:1"],
    }),
  );
  await rt.tickUntilIdle();
  const ticket = Object.values(rt.engine.state.tickets)[0];
  assert.ok(ticket);
  assert.deepEqual([...ticket.threadIds].sort(), ["github:o/r#pr:1", "im:group:1"]);
  assert.deepEqual(
    rt.engine.state.subscriptions.map((item) => item.threadId).sort(),
    ["github:o/r#pr:1", "im:group:1"],
  );
  rt.close();
});

test("同一 Thread 可被多个 Worker 订阅：新事件同时直通所有订阅者", async () => {
  const clock = new FakeClock();
  const executor = new RecordingExecutor();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([h.accept(), h.accept()]),
    executor,
    config: { dbPath: ":memory:", policy: h.policy() },
    clock,
  });
  rt.engine.ingest(h.trigger("trg-1", { threadIds: ["thr-a"] }));
  await rt.tickUntilIdle();
  rt.engine.ingest(h.trigger("trg-2", { threadIds: ["thr-b"] }));
  await rt.tickUntilIdle();
  const tickets = Object.values(rt.engine.state.tickets);
  assert.equal(tickets.length, 2);
  const second = tickets.find((ticket) => ticket.threadIds.includes("thr-b"));
  assert.ok(second);
  rt.store.appendAll([
    ev.subscriptionAdded({ ticketId: second.id, threadId: "thr-a", kind: "context" }, clock.now()),
  ]);

  rt.engine.ingest(h.trigger("trg-3", { threadIds: ["thr-a"] }));
  await rt.tickUntilIdle();
  const delivered = executor.delivered.filter((item) => item.input.ref === "trg-3");
  assert.equal(delivered.length, 2, "两个 Worker 都应收到同一 Thread 的事件");
  rt.close();
});

test("Correlation：任一线程的后续事件都直通同一个 Worker", async () => {
  const { rt, executor } = build();
  rt.engine.ingest(
    h.trigger("trg-1", {
      threadIds: ["im:group:1", "github:o/r#pr:1"],
      channelIds: ["im:group:1", "github:o/r#pr:1"],
    }),
  );
  await rt.tickUntilIdle();
  const ticket = Object.values(rt.engine.state.tickets)[0];
  assert.ok(ticket);

  rt.engine.ingest(
    h.trigger("trg-2", {
      text: "改为方案 B",
      threadIds: ["github:o/r#pr:1"],
      channelIds: ["github:o/r#pr:1"],
    }),
  );
  const state = rt.engine.state;
  assert.equal(state.dispositions["trg-2"], "fanned_out");
  await rt.tickUntilIdle();
  const inputs = Object.values(rt.engine.state.inputs).filter((input) => input.ticketId === ticket.id);
  assert.equal(inputs.length, 1);
  assert.equal(inputs[0]?.ref, "trg-2");
  assert.equal(executor.delivered.length, 1);
  rt.close();
});