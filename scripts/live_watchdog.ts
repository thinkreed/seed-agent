/**
 * 真实验收脚本：Watchdog + 模型裁定 + 重试。
 *
 * 用一个"永远不报告"的 worker 模拟卡死，观察：
 *   running assignment -> 超过 staleSeconds -> 模型判定 intervene -> 重试 -> 旧 worker 被停掉
 *
 * 运行：node scripts/live_watchdog.ts
 */

import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { App } from "../src/app.ts";
import { parseConfig } from "../src/config.ts";

const dir = mkdtempSync(join(tmpdir(), "seed-live-watchdog-"));
const inbox = join(dir, "inbox.jsonl");
writeFileSync(
  inbox,
  `${JSON.stringify({
    id: "trg-watchdog-live",
    source: "local",
    actor: "operator",
    text: "在当前工单目录创建 watchdog.txt，内容写 hello watchdog。完成后报告 ready。",
    threadIds: ["local:watchdog"],
    channelIds: ["local:watchdog"],
  })}\n`,
);

const config = parseConfig({
  dbPath: join(dir, "state.db"),
  workRoot: join(dir, "work"),
  slots: 1,
  intervalMs: 100,
  staleSeconds: 3,
  model: {
    baseUrl: process.env.SEED_MODEL_BASE_URL ?? "https://token-plan.maas.qianwenaiapi.com/compatible-mode/v1",
    apiKeyEnv: "BAILIAN_API_KEY",
    name: process.env.SEED_MODEL_NAME ?? "deepseek-v4.1-flash",
    temperature: 0,
  },
  sources: { local: { inbox } },
});

// 永远不报告、也不退出的 worker：模拟卡死
const app = App.create({
  config,
  workerCommand: { file: process.execPath, args: ["-e", "setTimeout(() => {}, 60000)"] },
});

const assignments: string[] = [];
const deadline = Date.now() + 60_000;
while (Date.now() < deadline) {
  await app.daemon.runRound();
  await app.runtime.tickUntilIdle();
  const state = app.runtime.engine.state;
  const list = Object.values(state.assignments);
  const snapshot = list.map((item) => `${item.id}:${item.state}`).join(",");
  if (!assignments.includes(snapshot) && snapshot) {
    assignments.push(snapshot);
    console.log(`assignments: ${snapshot}`);
  }
  const retried = list.some((item) => item.state === "ended");
  const relaunched = list.some((item) => item.state !== "ended");
  if (retried && relaunched) {
    console.log("WATCHDOG OK: 旧 assignment 已结束，新 assignment 已启动");
    break;
  }
  await new Promise((resolve) => setTimeout(resolve, 1000));
}

const state = app.runtime.engine.state;
console.log("tickets:", Object.values(state.tickets).map((item) => `${item.shortName}:${item.state}`).join(","));
console.log("retry 记录:", JSON.stringify(state.reports));
app.stop();