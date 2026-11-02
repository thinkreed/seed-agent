import assert from "node:assert/strict";
import { test } from "node:test";

import { ev } from "../src/builders.ts";
import type { AnyEvent } from "../src/events.ts";
import { apply, InvalidTransitionError, rebuild, UnknownEventError } from "../src/reducer.ts";
import { canonicalState } from "../src/store_hash.ts";
import * as h from "./helpers.ts";

function lifecycle(): AnyEvent[] {
  return [
    ev.policyChanged(h.policy(), 0),
    ev.triggerRecorded(h.trigger(), 1),
    ev.threadDeclared(h.thread(), 1),
    ev.evalQueued({ id: "eval-1", threadId: "thr-1", triggerIds: ["trg-1"], state: "queued", at: 1 }, 1),
    ev.evalStarted("eval-1", 2),
    ev.evalDecided("eval-1", h.accept(), 2),
    ev.ticketOpened(h.ticket(), 2),
    ev.subscriptionAdded(h.subscription(), 2),
    ev.assignmentCreated(h.assignment(), 3),
    ev.assignmentStarted("as-1", 3),
    ev.reportRecorded(h.report("ready", { summary: "done" }), 4),
    ev.assignmentEnded("as-1", "ready", 4),
    ev.ticketEnded("tk-1", "ready", "done", 4),
  ];
}

test("回放确定性：同一事件序列两次重建结果一致", () => {
  const first = rebuild(lifecycle());
  const second = rebuild(lifecycle());
  assert.equal(canonicalState(first), canonicalState(second));
  assert.equal(first.tickets["tk-1"]?.state, "ended");
  assert.deepEqual(first.reports["tk-1"]?.map((r) => r.status), ["ready"]);
});

test("未知事件被拒绝", () => {
  const bogus = { type: "nope.happened", data: {}, at: 0, seq: 0 } as unknown as AnyEvent;
  assert.throws(() => apply(rebuild([]), bogus), UnknownEventError);
});

test("非法转换：工单结束两次", () => {
  const state = rebuild(lifecycle());
  assert.throws(() => apply(state, ev.ticketEnded("tk-1", "ready", "again", 5)), InvalidTransitionError);
});

test("非法转换：eval 重复启动", () => {
  const state = rebuild(lifecycle().slice(0, 5));
  assert.throws(() => apply(state, ev.evalStarted("eval-1", 9)), InvalidTransitionError);
  assert.throws(() => apply(state, ev.evalStarted("ghost", 9)), InvalidTransitionError);
});

test("订阅幂等：重复添加同一条不产生重复", () => {
  let state = rebuild([ev.ticketOpened(h.ticket(), 0)]);
  state = apply(state, ev.subscriptionAdded(h.subscription(), 0));
  state = apply(state, ev.subscriptionAdded(h.subscription(), 0));
  assert.equal(state.subscriptions.length, 1);
});

test("被停止的工单不能 resume", () => {
  const state = rebuild([
    ev.policyChanged(h.policy(), 0),
    ev.ticketOpened(h.ticket(), 0),
    ev.ticketEnded("tk-1", "stopped", "stopped", 1),
  ]);
  assert.throws(() => apply(state, ev.ticketResumed("tk-1", 2)), InvalidTransitionError);
});

test("给未知工单写报告被拒绝", () => {
  assert.throws(
    () => apply(rebuild([]), ev.reportRecorded(h.report("ready", { ticketId: "ghost" }), 0)),
    InvalidTransitionError,
  );
});