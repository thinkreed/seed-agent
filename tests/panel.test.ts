import assert from "node:assert/strict";
import { test } from "node:test";

import { ev } from "../src/builders.ts";
import type { AnyEvent } from "../src/events.ts";
import { rebuild } from "../src/reducer.ts";
import { render, rows } from "../src/panel.ts";
import * as h from "./helpers.ts";

function stateWith(events: AnyEvent[] = []) {
  return rebuild([
    ev.policyChanged(h.policy(), 0),
    ev.ticketOpened(h.ticket(), 0),
    ev.subscriptionAdded(h.subscription(), 0),
    ...events,
  ]);
}

test("面板只列待处理的工单，不列空闲", () => {
  const state = stateWith([ev.assignmentCreated(h.assignment(), 1), ev.assignmentStarted("as-1", 1)]);
  const list = rows(state);
  assert.equal(list.length, 1);
  assert.equal(list[0]?.stage, "working");
  assert.equal(list[0]?.waitingPerson, false);
});

test("需要人的工单排在最前，并标记 waitingPerson", () => {
  const state = stateWith([
    ev.assignmentCreated(h.assignment(), 1),
    ev.assignmentStarted("as-1", 1),
    ev.reportRecorded(h.report("blocked"), 2),
  ]);
  const list = rows(state);
  assert.equal(list[0]?.stage, "person/blocked");
  assert.equal(list[0]?.waitingPerson, true);
});

test("结束的工单不出现在面板", () => {
  const state = stateWith([ev.ticketEnded("tk-1", "ready", "done", 3)]);
  assert.equal(rows(state).length, 0);
  assert.match(render(state), /nothing waits/);
});

test("render 输出可读表格", () => {
  const state = stateWith([]);
  const text = render(state);
  assert.match(text, /SHORT\s+STAGE/);
  assert.match(text, /t-000001/);
});