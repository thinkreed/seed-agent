/**
 * 真实验收脚本：进程重启恢复。
 *
 * 1. 用"永不报告"的 worker 制造一个 running assignment
 * 2. 模拟进程被杀（stop 掉 App）
 * 3. 重新装配 App 并 run()：recoverAfterRestart 应结束旧 assignment、投递 resume 输入、重新派工完成
 *
 * 运行：node scripts/live_recovery.ts
 */

import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { App } from "../src/app.ts";
import { parseConfig } from "../src/config.ts";

const dir = mkdtempSync(join(tmpdir(), "seed-live-recovery-"));
const inbox = join(dir, "inbox.jsonl");
writeFileSync(
  inbox,
  `${JSON.stringify({
    id: "trg-recovery-live",
    source: "local",
    actor: "operator",
    text: "在当前工单目录创建 recovery.txt，内容写 hello recovery。完成后报告 ready。",
    threadIds: ["local:recovery"],
    channelIds: ["local:recovery"],
  })}\n`,
);

const config = parseConfig({
  dbPath: join(dir, "state.db"),
  workRoot: join(dir, "work"),
  slots: 1,
  intervalMs: 100,
  staleSeconds: 3600,
  model: {
    baseUrl: process.env.SEED_MODEL_BASE_URL ?? "https://token-plan.maas.qianwenaiapi.com/compatible-mode/v1",
    apiKeyEnv: "BAILIAN_API_KEY",
    name: process.env.SEED_MODEL_NAME ?? "deepseek-v4.1-flash",
    temperature: 0,
  },
  sources: { local: { inbox } },
});

// 阶段 1：拉起一个永不报告的 worker，然后"进程被杀"
const phase1 = App.create({
  config,
  workerCommand: { file: process.execPath, args: ["-e", "setTimeout(() => {}, 60000)"] },
});
console.log("phase1 created");
await phase1.daemon.runRound();
console.log("phase1 round done");
await phase1.runtime.tickUntilIdle();
console.log("phase1 tick done");
const before = Object.values(phase1.runtime.engine.state.assignments);
console.log("阶段1 assignments:", before.map((item) => `${item.id}:${item.state}`).join(","));
phase1.stop();
console.log("phase1 stopped");
await new Promise((resolve) => setTimeout(resolve, 300));

// 阶段 2：模拟重启
console.log("phase2 creating");
const phase2 = App.create({ config });
console.log("phase2 created");
const running = phase2.run();
console.log("phase2 run started");
await new Promise((resolve) => setTimeout(resolve, 15_000));
console.log("phase2 15s elapsed");
const state = phase2.runtime.engine.state;
phase2.stop();
console.log("phase2 stopped");
await Promise.race([
  running.catch(() => undefined),
  new Promise((resolve) => setTimeout(resolve, 5_000)),
]);

const inputs = Object.values(state.inputs).map((item) => item.kind);
const assignments = Object.values(state.assignments).map((item) => `${item.id}:${item.state}`);
const tickets = Object.values(state.tickets).map((item) => `${item.shortName}:${item.state}`);
console.log("inputs:", inputs.join(","));
console.log("assignments:", assignments.join(","));
console.log("tickets:", tickets.join(","));
const ok = inputs.includes("resume");
console.log(ok ? "RECOVERY OK: 已投递 resume 输入" : "RECOVERY FAIL: 没有 resume 输入");
process.exit(ok ? 0 : 1);