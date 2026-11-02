import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { ev } from "../src/builders.ts";
import { SqliteStore } from "../src/store.ts";
import * as h from "./helpers.ts";

function tempDb(): { path: string; cleanup: () => void } {
  const dir = mkdtempSync(join(tmpdir(), "seed-store-"));
  return {
    path: join(dir, "events.db"),
    cleanup: () => rmSync(dir, { recursive: true, force: true }),
  };
}

test("append / events / state：事件只追加，状态可重建", () => {
  const store = new SqliteStore();
  store.append(ev.policyChanged(h.policy(), 0));
  store.append(ev.triggerRecorded(h.trigger(), 1));
  store.append(ev.threadDeclared(h.thread(), 1));
  assert.equal(store.lastSeq(), 3);
  assert.equal(store.events().length, 3);
  assert.equal(store.events(2).length, 1);
  assert.equal(Object.keys(store.state().triggers).length, 1);
  store.close();
});

test("持久化：关闭后重开，状态与回放哈希一致", () => {
  const db = tempDb();
  try {
    const first = new SqliteStore(db.path);
    first.append(ev.policyChanged(h.policy(), 0));
    first.append(ev.triggerRecorded(h.trigger(), 1));
    first.append(ev.threadDeclared(h.thread(), 1));
    const hash = first.replayHash();
    first.close();

    const second = new SqliteStore(db.path);
    assert.equal(second.replayHash(), hash);
    assert.equal(second.lastSeq(), 3);
    second.close();
  } finally {
    db.cleanup();
  }
});

test("cursors：读写位点", () => {
  const store = new SqliteStore();
  assert.equal(store.cursorGet("github"), null);
  store.cursorSet("github", "12345", 100);
  assert.equal(store.cursorGet("github"), "12345");
  store.cursorSet("github", "12346", 101);
  assert.equal(store.cursorGet("github"), "12346");
  store.close();
});

test("outbox：入队、到期、标记", () => {
  const store = new SqliteStore();
  store.outboxEnqueue("eff-1", "launch", { assignmentId: "as-1" }, 10);
  assert.equal(store.outboxDue(9).length, 0);
  const due = store.outboxDue(10);
  assert.equal(due.length, 1);
  assert.equal(due[0]?.payload.assignmentId, "as-1");
  store.outboxMark("eff-1", "done", 0, 10);
  assert.equal(store.outboxDue(10).length, 0);
  assert.equal(store.outboxGet("eff-1")?.state, "done");
  store.close();
});

test("未知事件不会入账", () => {
  const store = new SqliteStore();
  assert.throws(() =>
    store.append({ type: "nope", data: {}, at: 0, seq: 0 } as never),
  );
  assert.equal(store.lastSeq(), 0);
  store.close();
});