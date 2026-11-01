import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { ev } from "../src/builders.ts";
import type { AnyEvent } from "../src/events.ts";
import { EVENT_TYPES, REQUIRED_KEYS } from "../src/events.ts";
import { apply } from "../src/reducer.ts";
import { emptyState } from "../src/domain.ts";
import { UnknownEventError } from "../src/reducer.ts";
import * as h from "./helpers.ts";

const SRC = join(import.meta.dirname, "..", "src");

function sourceFiles(): string[] {
  return readdirSync(SRC).filter((name) => name.endsWith(".ts"));
}

test("每个源文件 ≤ 210 行（拆分纪律）", () => {
  for (const name of sourceFiles()) {
    const lines = readFileSync(join(SRC, name), "utf8").split("\n").length;
    assert.ok(lines <= 210, `${name} has ${lines} lines`);
  }
});

test("SQLite 只允许出现在 store.ts", () => {
  for (const name of sourceFiles()) {
    if (name === "store.ts") continue;
    const content = readFileSync(join(SRC, name), "utf8");
    assert.ok(!content.includes("node:sqlite"), `${name} must not import node:sqlite`);
  }
});

test("时间只能来自 clock.ts", () => {
  for (const name of sourceFiles()) {
    if (name === "clock.ts") continue;
    const content = readFileSync(join(SRC, name), "utf8");
    assert.ok(!content.includes("Date.now"), `${name} must use Clock instead of Date.now`);
  }
});

test("事件类型表与必填字段一一对应", () => {
  assert.deepEqual([...EVENT_TYPES].sort(), Object.keys(REQUIRED_KEYS).sort());
});

test("每个事件都有 reducer 分支（未知事件才抛 UnknownEventError）", () => {
  const samples: Record<string, AnyEvent> = {
    "trigger.recorded": ev.triggerRecorded(h.trigger(), 0),
    "thread.declared": ev.threadDeclared(h.thread(), 0),
    "trigger.filtered": ev.triggerFiltered("trg-1", "fast", "no", 0),
    "disposition.recorded": ev.dispositionRecorded("trg-1", "filtered", 0),
    "eval.queued": ev.evalQueued({ id: "eval-1", threadId: "thr-1", triggerIds: [], state: "queued", at: 0 }, 0),
    "eval.started": ev.evalStarted("eval-1", 0),
    "eval.decided": ev.evalDecided("eval-1", h.accept(), 0),
    "ticket.opened": ev.ticketOpened(h.ticket(), 0),
    "ticket.ended": ev.ticketEnded("tk-1", "ready", "done", 0),
    "ticket.resumed": ev.ticketResumed("tk-1", 0),
    "subscription.added": ev.subscriptionAdded(h.subscription(), 0),
    "subscription.removed": ev.subscriptionRemoved("tk-1", "thr-1", 0),
    "assignment.created": ev.assignmentCreated(h.assignment(), 0),
    "assignment.started": ev.assignmentStarted("as-1", 0),
    "assignment.ended": ev.assignmentEnded("as-1", "ready", 0),
    "input.fanned_out": ev.inputFannedOut(h.input(), 0),
    "input.delivered": ev.inputDelivered("inp-1", 0),
    "input.undelivered": ev.inputUndelivered("inp-1", "down", 0),
    "report.recorded": ev.reportRecorded(h.report("progress"), 0),
    "attention.opened": ev.attentionOpened(h.attention(), 0),
    "message.queued": ev.messageQueued(
      { id: "msg-1", ticketId: "tk-1", channelId: "chan-1", address: "chan-1", text: "hi", at: 0 },
      0,
    ),
    "message.sent": ev.messageSent("msg-1", 0),
    "message.failed": ev.messageFailed("msg-1", "down", 0),
    "policy.changed": ev.policyChanged(h.policy(), 0),
  };
  assert.deepEqual(Object.keys(samples).sort(), [...EVENT_TYPES].sort());

  for (const [type, event] of Object.entries(samples)) {
    try {
      apply(emptyState(), event);
    } catch (error) {
      assert.ok(!(error instanceof UnknownEventError), `${type} has no reducer branch`);
    }
  }
});