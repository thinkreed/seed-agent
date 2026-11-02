import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { startHttpDaemon } from "../src/daemon/http.ts";
import { SqliteStore } from "../src/store.ts";

test("磁盘/路径故障：数据库父路径是文件时启动失败而不是静默", () => {
  const dir = mkdtempSync(join(tmpdir(), "seed-fault-disk-"));
  try {
    const blocker = join(dir, "not-a-directory");
    writeFileSync(blocker, "x");
    assert.throws(() => new SqliteStore(join(blocker, "seed.db")));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("daemon 故障注入：坏 JSON 返回 500，进程仍健康", async () => {
  const root = mkdtempSync(join(tmpdir(), "seed-fault-json-"));
  const daemon = await startHttpDaemon({ root, clock: new FakeClock() });
  try {
    const bad = await fetch(`http://127.0.0.1:${daemon.port}/request`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{not-json",
    });
    assert.equal(bad.status, 500);
    const health = await fetch(`http://127.0.0.1:${daemon.port}/health`);
    assert.equal(health.status, 200);
  } finally {
    await daemon.close();
    rmSync(root, { recursive: true, force: true });
  }
});