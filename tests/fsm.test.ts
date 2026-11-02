import assert from "node:assert/strict";
import { test } from "node:test";

import { ev } from "../src/builders.ts";
import { apply, rebuild } from "../src/reducer.ts";
import { requiresPerson, stageOf } from "../src/fsm.ts";
import * as h from "./helpers.ts";

function base() {
  return rebuild([
    ev.policyChanged(h.policy(), 0),
    ev.ticketOpened(h.ticket(), 0),
    ev.subscriptionAdded(h.subscription(), 0),
  ]);
}

test("没有 assignment -> working/queued", () => {
  const state = base();
  assert.equal(stageOf(state, h.ticket()), "working/queued");
});

test("assignment pending -> working/queued", () => {
  const state = rebuild([...eventsOf(base()), ev.assignmentCreated(h.assignment(), 1)]);
  assert.equal(stageOf(state, h.ticket()), "working/queued");
});

test("assignment running -> working", () => {
  const state = rebuild([
    ...eventsOf(base()),
    ev.assignmentCreated(h.assignment(), 1),
    ev.assignmentStarted("as-1", 1),
  ]);
  assert.equal(stageOf(state, h.ticket()), "working");
});

test("ready 报告 -> person/review", () => {
  const state = rebuild([
    ...eventsOf(base()),
    ev.assignmentCreated(h.assignment(), 1),
    ev.assignmentStarted("as-1", 1),
    ev.reportRecorded(h.report("ready"), 2),
  ]);
  assert.equal(stageOf(state, h.ticket()), "person/review");
  assert.equal(requiresPerson("person/review"), true);
});

test("waiting 报告 + assignment 结束 -> idle", () => {
  const state = rebuild([
    ...eventsOf(base()),
    ev.assignmentCreated(h.assignment(), 1),
    ev.assignmentStarted("as-1", 1),
    ev.reportRecorded(h.report("waiting"), 2),
    ev.assignmentEnded("as-1", "waiting", 2),
  ]);
  assert.equal(stageOf(state, h.ticket()), "idle");
});

test("blocked 报告 -> person/blocked；人发言后回到 working", () => {
  const blocked = rebuild([
    ...eventsOf(base()),
    ev.assignmentCreated(h.assignment(), 1),
    ev.assignmentStarted("as-1", 1),
    ev.reportRecorded(h.report("blocked"), 2),
  ]);
  assert.equal(stageOf(blocked, h.ticket()), "person/blocked");

  const released = apply(blocked, ev.inputFannedOut(h.input("inp-9", { kind: "text", at: 3 }), 3));
  assert.equal(stageOf(released, h.ticket()), "working");
});

test("attention -> person/answer", () => {
  const state = rebuild([...eventsOf(base()), ev.attentionOpened(h.attention(), 1)]);
  assert.equal(stageOf(state, h.ticket()), "person/answer");
});

test("投递失败 -> person/delivery", () => {
  const state = rebuild([
    ...eventsOf(base()),
    ev.inputFannedOut(h.input("inp-1"), 1),
    ev.inputUndelivered("inp-1", "session down", 1),
  ]);
  assert.equal(stageOf(state, h.ticket()), "person/delivery");
  assert.equal(requiresPerson("person/delivery"), true);
});

test("结束的工单 -> idle", () => {
  const state = rebuild([...eventsOf(base()), ev.ticketEnded("tk-1", "ready", "done", 3)]);
  const ticket = state.tickets["tk-1"];
  assert.ok(ticket);
  assert.equal(stageOf(state, ticket), "idle");
});

test("requiresPerson：working/idle 不需要人", () => {
  assert.equal(requiresPerson("working"), false);
  assert.equal(requiresPerson("idle"), false);
  assert.equal(requiresPerson("working/queued"), false);
});

/** 把 state 还原成事件列表（测试里只需要事件序列，便于拼接）。 */
function eventsOf(_state: unknown) {
  return [
    ev.policyChanged(h.policy(), 0),
    ev.ticketOpened(h.ticket(), 0),
    ev.subscriptionAdded(h.subscription(), 0),
  ];
}