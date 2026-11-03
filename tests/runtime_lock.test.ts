import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { acquireRuntimeLock, runtimeLockHeld } from "../src/runtime_lock.ts";

test("同一个事件库只允许一个 Runtime 持锁", () => {
  const dir = mkdtempSync(join(tmpdir(), "seed-lock-"));
  const db = join(dir, "seed.db");
  const first = acquireRuntimeLock(db);
  assert.equal(runtimeLockHeld(db), true);
  assert.throws(() => acquireRuntimeLock(db), /runtime already active/);
  first.release();
  assert.equal(runtimeLockHeld(db), false);
  const second = acquireRuntimeLock(db);
  second.release();
  rmSync(dir, { recursive: true, force: true });
});