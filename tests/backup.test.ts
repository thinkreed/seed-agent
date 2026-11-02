import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { ev } from "../src/builders.ts";
import { SqliteStore } from "../src/store.ts";
import { backupStore } from "../src/store_backup.ts";
import * as h from "./helpers.ts";

test("SQLite 在线备份：快照可打开且回放哈希一致", () => {
  const dir = mkdtempSync(join(tmpdir(), "seed-backup-"));
  try {
    const source = new SqliteStore(join(dir, "live.db"));
    source.append(ev.policyChanged(h.policy(), 0));
    source.append(ev.triggerRecorded(h.trigger("trg-1"), 1));
    const before = source.replayHash();

    backupStore(source, join(dir, "backup", "snapshot.db"));
    source.close();

    const restored = new SqliteStore(join(dir, "backup", "snapshot.db"));
    assert.equal(restored.replayHash(), before);
    assert.equal(Object.keys(restored.state().triggers).length, 1);
    restored.close();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});