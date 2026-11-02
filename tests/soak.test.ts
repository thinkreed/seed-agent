import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { Runtime } from "../src/runtime.ts";
import { SqliteStore } from "../src/store.ts";
import { RecordingExecutor, ScriptedAssessor } from "./fakes.ts";
import * as h from "./helpers.ts";

test("soak：500 条追加事件 + 100 次重复投递，全部直通且状态可重放", async () => {
  const dir = mkdtempSync(join(tmpdir(), "seed-soak-"));
  const dbPath = join(dir, "state.db");
  try {
    const clock = new FakeClock();
    const executor = new RecordingExecutor();
    const rt = Runtime.build({
      assessor: new ScriptedAssessor([h.accept()]),
      executor,
      config: { dbPath, policy: h.policy(), slots: 2 },
      clock,
    });
    rt.engine.ingest(h.trigger("trg-root", { threadIds: ["thr-soak"], channelIds: ["ch-soak"] }));
    await rt.tickUntilIdle();
    assert.equal(Object.keys(rt.engine.state.tickets).length, 1);

    for (let index = 0; index < 500; index += 1) {
      rt.engine.ingest(
        h.trigger(`trg-${index}`, {
          threadIds: ["thr-soak"],
          channelIds: ["ch-soak"],
          text: `follow-up ${index}`,
          at: index + 2,
        }),
      );
    }
    // 重复投递 100 次：引擎必须幂等。
    for (let index = 0; index < 100; index += 1) {
      rt.engine.ingest(h.trigger(`trg-${index}`, { threadIds: ["thr-soak"] }));
    }
    await rt.tickUntilIdle();

    const state = rt.engine.state;
    assert.equal(Object.keys(state.triggers).length, 501);
    assert.equal(executor.delivered.length, 500);
    assert.equal(new Set(executor.delivered.map((item) => item.input.ref)).size, 500);
    const hash = rt.store.replayHash();
    rt.close();

    const reopened = new SqliteStore(dbPath);
    assert.equal(reopened.replayHash(), hash);
    reopened.close();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});