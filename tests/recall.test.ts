import assert from "node:assert/strict";
import { test } from "node:test";

import { ev } from "../src/builders.ts";
import { DEFAULT_BUDGET } from "../src/context.ts";
import { rebuild } from "../src/reducer.ts";
import { recall } from "../src/recall.ts";
import * as h from "./helpers.ts";

function state() {
  return rebuild([
    ev.policyChanged(h.policy(), 0),
    ev.threadDeclared(h.thread(), 0),
    ev.triggerRecorded(h.trigger("trg-1", { text: "修复登录页 500", at: 1 }), 1),
    ev.triggerRecorded(h.trigger("trg-2", { text: "补充单元测试", at: 2 }), 2),
    ev.ticketOpened(h.ticket(), 2),
    ev.subscriptionAdded(h.subscription(), 2),
    ev.assignmentCreated(h.assignment(), 3),
    ev.reportRecorded(h.report("waiting", { summary: "等 CI" }), 4),
  ]);
}

test("recall trigger：返回完整文本与下一跳 handle", () => {
  const result = recall(state(), "trigger", "trg-1");
  assert.equal(result.found, true);
  assert.match(result.text, /修复登录页/);
  assert.ok(result.handles.some((handle) => handle.kind === "thread"));
  assert.ok(result.handles.some((handle) => handle.kind === "ticket"));
});

test("recall thread：汇总计数与最近消息，带触发与工单 handle", () => {
  const result = recall(state(), "thread", "thr-1");
  assert.equal(result.found, true);
  assert.match(result.summary, /triggers=2/);
  assert.match(result.summary, /tickets=1/);
  assert.match(result.text, /trg-2/);
  assert.ok(result.handles.some((handle) => handle.kind === "trigger"));
  assert.ok(result.handles.some((handle) => handle.kind === "ticket"));
});

test("recall ticket：带阶段、授权与最近报告，并指回线程", () => {
  const result = recall(state(), "ticket", "tk-1");
  assert.equal(result.found, true);
  assert.match(result.summary, /stage=/);
  assert.match(result.text, /waiting/);
  assert.deepEqual(result.handles, [{ kind: "thread", id: "thr-1" }]);
});

test("recall：不存在时返回 found=false，不抛错", () => {
  const result = recall(state(), "ticket", "tk-ghost");
  assert.equal(result.found, false);
  assert.equal(result.handles.length, 0);
});

test("recall：文本按 inlineChars 截断", () => {
  const long = rebuild([
    ev.threadDeclared(h.thread(), 0),
    ev.triggerRecorded(h.trigger("trg-1", { text: "z".repeat(500) }), 0),
  ]);
  const result = recall(long, "trigger", "trg-1", { ...DEFAULT_BUDGET, inlineChars: 50 });
  assert.equal(result.text.length, 51);
});