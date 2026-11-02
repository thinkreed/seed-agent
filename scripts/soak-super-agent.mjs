/**
 * 引擎 soak：批量追加事件 + 重复投递 + 重放校验，打印吞吐。
 *
 *   node --no-warnings scripts/soak-super-agent.mjs [events]
 *
 * 用真实 Runtime/Engine/Store；评估器与执行器是确定性替身，因此可重复、零网络。
 */

import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { FakeClock } from "../src/clock.ts";
import { Runtime } from "../src/runtime.ts";
import { SqliteStore } from "../src/store.ts";

const total = Number(process.argv[2] ?? 5000);
const dir = mkdtempSync(join(tmpdir(), "seed-soak-"));
const dbPath = join(dir, "state.db");
const clock = new FakeClock();

const policy = {
  version: "soak",
  acceptMode: "auto",
  allowedSenders: [["local", "*"]],
  rules: [{ source: "local", actor: "*", allow: true, strength: "explicit", note: "soak" }],
};
const delivered = [];
const executor = {
  launch: () => undefined,
  deliver: (_ticket, input) => delivered.push(input),
  stop: () => undefined,
};
const accept = {
  kind: "accept",
  strength: "explicit",
  reason: "soak",
  rules: [],
  scope: "ticket",
};

const rt = Runtime.build({
  assessor: { assess: () => accept },
  executor,
  config: { dbPath, policy, slots: 4 },
  clock,
});
const trigger = (id, overrides = {}) => ({
  id,
  source: "local",
  actor: "alice",
  text: `event ${id}`,
  threadIds: ["thr-soak"],
  channelIds: ["ch-soak"],
  at: 1,
  ...overrides,
});

const started = performance.now();
rt.engine.ingest(trigger("trg-root"));
await rt.tickUntilIdle();

for (let index = 0; index < total; index += 1) {
  rt.engine.ingest(trigger(`trg-${index}`, { at: index + 2 }));
}
for (let index = 0; index < Math.floor(total / 5); index += 1) {
  rt.engine.ingest(trigger(`trg-${index}`));
}
await rt.tickUntilIdle();
const ms = performance.now() - started;

const state = rt.engine.state;
const hash = rt.store.replayHash();
const events = rt.store.lastSeq();
rt.close();
const reopened = new SqliteStore(dbPath);
const replayOk = reopened.replayHash() === hash;
reopened.close();
rmSync(dir, { recursive: true, force: true });

console.log(
  JSON.stringify(
    {
      events,
      uniqueTriggers: Object.keys(state.triggers).length,
      delivered: delivered.length,
      tickets: Object.keys(state.tickets).length,
      ms: Math.round(ms),
      eventsPerSecond: Math.round((events / ms) * 1000),
      replayOk,
    },
    null,
    2,
  ),
);
console.log(replayOk ? "SOAK OK" : "SOAK FAIL");
process.exitCode = replayOk ? 0 : 1;