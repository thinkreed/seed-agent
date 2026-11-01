/**
 * Worker 进程入口（真实执行会话）。
 *
 * 环境变量：
 *   SEED_WORKER_ROOT          工单目录（工作区根）
 *   SEED_WORKER_TICKET        工单 ID
 *   SEED_WORKER_SHORT_NAME    工单短名
 *   SEED_WORKER_SCOPE         授权范围
 *   SEED_WORKER_INPUT         初始输入的 JSON（Trigger 数组）
 *   SEED_MODEL_BASE_URL       模型端点（OpenAI 兼容）
 *   SEED_MODEL_API_KEY        模型密钥
 *   SEED_MODEL_NAME           模型名
 *   SEED_WORKER_MAX_STEPS     每轮最多几步（默认 12）
 *
 * stdin：逐行 JSON，形如 {"inputId","kind","ref"}，代表 daemon 投递的新输入。
 * stdout：逐行 JSON 报告 {"type":"report","status","summary"}。
 */

import { createInterface } from "node:readline";

import { SystemClock } from "../clock.ts";
import type { Ticket, Trigger } from "../domain.ts";
import { JobRegistry } from "../jobs.ts";
import { OpenAIClient } from "../llm/openai.ts";
import { ReactLoop } from "../react.ts";
import { fileTools } from "../tools/files.ts";
import { shellTool } from "../tools/shell.ts";

function env(name: string, fallback = ""): string {
  return process.env[name] ?? fallback;
}

function required(name: string): string {
  const value = env(name);
  if (!value) {
    process.stderr.write(`missing env: ${name}\n`);
    process.exit(2);
  }
  return value;
}

function parseInputs(raw: string): Trigger[] {
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is Trigger => typeof item === "object" && item !== null);
  } catch {
    return [];
  }
}

const root = required("SEED_WORKER_ROOT");
const ticket: Ticket = {
  id: env("SEED_WORKER_TICKET", "tk-local"),
  shortName: env("SEED_WORKER_SHORT_NAME", "t-local"),
  mandate: {
    policyVersion: "",
    strength: "explicit",
    scope: env("SEED_WORKER_SCOPE", "ticket"),
    source: "worker",
    actor: "",
    rules: [],
    triggerId: "",
  },
  threadIds: [],
  channelIds: [],
  state: "open",
  stopped: false,
  createdAt: 0,
};

const clock = new SystemClock();
const jobs = new JobRegistry(clock, { maxRunSeconds: 1800 });
const model = new OpenAIClient({
  baseUrl: required("SEED_MODEL_BASE_URL"),
  apiKey: required("SEED_MODEL_API_KEY"),
  model: required("SEED_MODEL_NAME"),
});
const loop = new ReactLoop({
  model,
  tools: {
    ...fileTools(root),
    run_shell: shellTool({ root }),
  },
  jobs,
  clock,
  maxSteps: Number(env("SEED_WORKER_MAX_STEPS", "12")),
});

function emit(status: string, summary: string): void {
  process.stdout.write(`${JSON.stringify({ type: "report", status, summary })}\n`);
}

const inbox: Trigger[] = parseInputs(env("SEED_WORKER_INPUT"));
let running = false;
let closed = false;

async function kick(): Promise<void> {
  if (running) return;
  running = true;
  while (inbox.length > 0) {
    const batch = inbox.splice(0, inbox.length);
    const report = await loop.run(ticket, batch);
    emit(report.status, report.summary);
    if (report.status !== "progress" && report.status !== "waiting") break;
  }
  running = false;
  if (closed && inbox.length === 0) process.exit(0);
}

createInterface({ input: process.stdin }).on("line", (line) => {
  const raw = line.trim();
  if (!raw) return;
  try {
    const payload = JSON.parse(raw) as { inputId?: string; kind?: string; ref?: string };
    inbox.push({
      id: payload.inputId ?? `inp-${inbox.length}`,
      source: "worker",
      actor: "router",
      text: payload.ref ?? "",
      threadIds: [],
      channelIds: [],
      at: clock.now(),
    });
  } catch {
    return;
  }
  void kick();
});

process.stdin.on("close", () => {
  closed = true;
  if (!running) void kick();
});

if (inbox.length > 0) void kick();