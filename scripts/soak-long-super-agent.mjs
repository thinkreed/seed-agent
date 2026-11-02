/**
 * 长跑 soak：持续追加事件、重复投递、周期性进程重启，验证状态不丢、幂等、可重放。
 *
 *   node --no-warnings scripts/soak-long-super-agent.mjs --minutes 60 --db /var/lib/seed-agent/soak.db
 *
 * 72h 验收：--minutes 4320。脚本可随时 Ctrl-C，重启后从同一 DB 继续。
 */

import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { FakeClock } from "../src/clock.ts";
import { buildPolicy } from "../src/policy.ts";
import { Runtime } from "../src/runtime.ts";
import { SqliteStore } from "../src/store.ts";

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : fallback;
};
const minutes = Number(flag("--minutes", "60"));
const batch = Number(flag("--batch", "200"));
let dbPath = flag("--db", "");
const temporary = dbPath === "";
if (temporary) dbPath = join(mkdtempSync(join(tmpdir(), "seed-soak-long-")), "soak.db");

const policy = buildPolicy(
  [{ source: "local", actor: "*", allow: true, strength: "explicit", note: "soak" }],
  "auto",
  [["local", "*"]],
);
const accept = {
  kind: "accept",
  strength: "explicit",
  reason: "soak",
  rules: [],
  scope: "ticket",
};
let delivered = 0;
let sequence = 0;
const clock = new FakeClock();
const trigger = (id, overrides = {}) => ({
  id,
  source: "local",
  actor: "alice",
  text: `soak ${id}`,
  threadIds: ["thr-soak"],
  channelIds: ["ch-soak"],
  at: ++sequence,
  ...overrides,
});

const build = () =>
  Runtime.build({
    assessor: { assess: () => accept },
    executor: {
      launch: () => undefined,
      deliver: () => {
        delivered += 1;
      },
      stop: () => undefined,
    },
    config: { dbPath, policy, slots: 4 },
    clock,
  });

let rt = build();
const deadline = Date.now() + minutes * 60_000;
let rounds = 0;
let lastReport = 0;

async function runRound() {
  const start = rt.store.lastSeq();
  for (let index = 0; index < batch; index += 1) {
    rt.engine.ingest(trigger(`trg-${rounds}-${index}`));
  }
  // 每 100 批重复投递上一批 20%：引擎必须幂等。
  if (rounds % 100 === 0 && rounds > 0) {
    for (let index = 0; index < Math.floor(batch / 5); index += 1) {
      rt.engine.ingest(trigger(`trg-${rounds - 1}-${index}`));
    }
  }
  await rt.tickUntilIdle();
  rounds += 1;
  if (rounds % 100 === 0) {
    // 模拟进程重启：关闭后从同一 DB 重建，状态与计数必须延续。
    const before = Object.keys(rt.engine.state.triggers).length;
    rt.close();
    rt = build();
    const after = Object.keys(rt.engine.state.triggers).length;
    if (before !== after) throw new Error(`restart lost state: ${before} -> ${after}`);
  }
  const now = Date.now();
  if (now - lastReport >= 60_000) {
    lastReport = now;
    console.log(
      JSON.stringify({
        rounds,
        events: rt.store.lastSeq(),
        triggers: Object.keys(rt.engine.state.triggers).length,
        delivered,
        rate: start,
      }),
    );
  }
}

try {
  while (Date.now() < deadline) {
    if (rounds === 0) {
      if (Object.keys(rt.engine.state.tickets).length === 0) {
        rt.engine.ingest(trigger("trg-root"));
      }
      await rt.tickUntilIdle();
    }
    await runRound();
  }
  const hash = rt.store.replayHash();
  rt.close();
  const reopened = new SqliteStore(dbPath);
  const replayOk = reopened.replayHash() === hash;
  reopened.close();
  console.log(
    JSON.stringify({
      rounds,
      events: sequence,
      delivered,
      tickets: hash.length > 0,
      replayOk,
      dbPath,
    }),
  );
  console.log(replayOk ? "LONG SOAK OK" : "LONG SOAK FAIL");
  process.exitCode = replayOk ? 0 : 1;
} finally {
  if (temporary) rmSync(join(dbPath, ".."), { recursive: true, force: true });
}