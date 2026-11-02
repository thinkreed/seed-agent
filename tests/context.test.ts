import assert from "node:assert/strict";
import { test } from "node:test";

import { ev } from "../src/builders.ts";
import { buildAssessmentView, buildView, clip, DEFAULT_BUDGET } from "../src/context.ts";
import { rebuild } from "../src/reducer.ts";
import * as h from "./helpers.ts";

function stateWith(options: { triggers?: number; text?: string; ticket?: boolean } = {}) {
  const count = options.triggers ?? 1;
  const events = [
    ev.policyChanged(h.policy(), 0),
    ev.threadDeclared(h.thread(), 0),
    ...Array.from({ length: count }, (_, index) =>
      ev.triggerRecorded(
        h.trigger(`trg-${String(index + 1).padStart(3, "0")}`, {
          text: options.text ?? `message ${index + 1}`,
          at: index,
        }),
        index,
      ),
    ),
  ];
  if (options.ticket !== false) {
    events.push(ev.ticketOpened(h.ticket(), 1), ev.subscriptionAdded(h.subscription(), 1));
  }
  return rebuild(events);
}

test("buildView：同 Thread 的历史事件作为时空相邻上下文内联", () => {
  const batch = h.trigger("trg-2", { text: "改为方案 B", at: 2 });
  const history = h.trigger("trg-1", { text: "先按方案 A", at: 1 });
  const view = buildView({
    threadId: "thr-1",
    triggers: [batch],
    history: [history],
    tickets: [],
    policy: h.policy(),
  });
  assert.deepEqual(view.triggers.map((trigger) => trigger.id), ["trg-1", "trg-2"]);
  assert.ok(view.handles.some((handle) => handle.kind === "trigger" && handle.id === "trg-1"));
});

test("clip：短文本原样返回，长文本截断并标记", () => {
  const short = clip("hello", 100);
  assert.deepEqual(short, { text: "hello", truncated: false, chars: 5 });

  const long = clip("x".repeat(300), 100);
  assert.equal(long.truncated, true);
  assert.equal(long.chars, 300);
  assert.equal(long.text.length, 101);
});

test("clip：统一换行符", () => {
  assert.equal(clip("a\r\nb", 100).text, "a\nb");
});

test("view：Inline 最近 N 条，更早的 Spill 成 handle", () => {
  const state = stateWith({ triggers: 15 });
  const view = buildAssessmentView(state, "thr-1", { ...DEFAULT_BUDGET, maxTriggers: 12 });
  assert.equal(view.triggers.length, 12);
  assert.equal(view.spilled.length, 3);
  assert.deepEqual(view.spilled.map((item) => item.id), ["trg-001", "trg-002", "trg-003"]);
  assert.equal(view.triggers[0]?.id, "trg-004");
});

test("view：超长文本被截断并保留 recall 入口", () => {
  const state = stateWith({ text: "y".repeat(500) });
  const view = buildAssessmentView(state, "thr-1", { ...DEFAULT_BUDGET, spillChars: 100 });
  assert.equal(view.triggers[0]?.text.truncated, true);
  assert.equal(view.triggers[0]?.text.chars, 500);
});

test("view：handles 含线程、内联 Trigger 与工单 ID", () => {
  const state = stateWith({ triggers: 2 });
  const view = buildAssessmentView(state, "thr-1");
  const kinds = view.handles.map((handle) => handle.kind);
  assert.ok(kinds.includes("thread"));
  assert.ok(kinds.includes("trigger"));
  assert.ok(kinds.includes("ticket"));
  assert.equal(view.policyVersion, h.policy().version);
});

test("view：工单视图带阶段与授权信息；同输入输出完全一致", () => {
  const state = stateWith({ triggers: 2 });
  const first = buildAssessmentView(state, "thr-1");
  const second = buildAssessmentView(state, "thr-1");
  assert.equal(JSON.stringify(first), JSON.stringify(second));
  const ticket = first.tickets[0];
  assert.ok(ticket);
  assert.equal(ticket.stage, "working/queued");
  assert.equal(ticket.scope, "ticket");
  assert.equal(ticket.strength, "explicit");
});

test("view：空线程不会崩，返回空集合", () => {
  const state = stateWith({ triggers: 0, ticket: false });
  const view = buildAssessmentView(state, "thr-none");
  assert.deepEqual(view.triggers, []);
  assert.deepEqual(view.tickets, []);
  assert.equal(view.spilled.length, 0);
});