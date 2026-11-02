/**
 * 逐条跑通文章能力的现场演示（不是测试套件）。
 *
 *   node --no-warnings scripts/demo-article.mjs
 *
 * 用真实产品模块：Runtime / RouterSession / Engine / JobRegistry / ReactLoop /
 * channel adapters / SQLite store / HTTP daemon / RemoteExecutor / Watchdog。
 * 没有模型凭证时，用本地 HTTP mock 充当 OpenAI 兼容端点；Worker 进程是真实子进程。
 */

import { createServer } from "node:http";
import { mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { FakeClock } from "../src/clock.ts";
import { buildPolicy } from "../src/policy.ts";
import { Runtime } from "../src/runtime.ts";
import { RouterSession } from "../src/router_session.ts";
import { OpenAIClient } from "../src/llm/openai.ts";
import { buildView } from "../src/context.ts";
import { recall } from "../src/recall.ts";
import { Speculator } from "../src/speculation.ts";
import { reactSpeculationRunner } from "../src/speculation_react.ts";
import { JobRegistry } from "../src/jobs.ts";
import { ReactLoop } from "../src/react.ts";
import { subagentTool } from "../src/subagent_tool.ts";
import { compactForIm, structureForAsync } from "../src/format.ts";
import { DocsChannel } from "../src/channels/docs.ts";
import { EmailDraftChannel } from "../src/channels/email.ts";
import { SqliteStore } from "../src/store.ts";
import { startHttpDaemon } from "../src/daemon/http.ts";
import { HttpTransport } from "../src/executor/http.ts";
import { RemoteExecutor } from "../src/executor/remote.ts";
import { Watchdog } from "../src/watchdog.ts";
import { WatchdogController } from "../src/control.ts";
import { ev } from "../src/builders.ts";

let passed = 0;
let failed = 0;

function check(label, ok, detail) {
  if (ok) passed += 1;
  else failed += 1;
  console.log(`${ok ? "✅" : "❌"} ${label}${detail ? ` — ${detail}` : ""}`);
}

const policy = buildPolicy(
  [{ source: "local", actor: "*", allow: true, strength: "explicit", note: "demo" }],
  "auto",
  [["local", "alice"]],
);

const accept = {
  kind: "accept",
  strength: "explicit",
  reason: "demo",
  rules: [],
  scope: "ticket",
};

function trigger(id, overrides = {}) {
  return {
    id,
    source: "local",
    actor: "alice",
    text: "处理这个请求",
    threadIds: ["thr-A"],
    channelIds: ["local:A"],
    at: 1,
    ...overrides,
  };
}

function ticket(id = "tk-demo") {
  return {
    id,
    shortName: "t-demo",
    mandate: {
      policyVersion: policy.version,
      strength: "explicit",
      scope: "ticket",
      source: "local",
      actor: "alice",
      rules: [],
      triggerId: "trg-1",
    },
    threadIds: ["thr-A"],
    channelIds: ["local:A"],
    state: "open",
    stopped: false,
    createdAt: 1,
  };
}

function assignment(id = "as-demo") {
  return { id, ticketId: "tk-demo", state: "pending", executorRef: "", createdAt: 1 };
}

function captureExecutor() {
  return {
    launched: [],
    delivered: [],
    stopped: [],
    launch(a, t) {
      this.launched.push({ assignment: a, ticket: t });
    },
    deliver(t, i) {
      this.delivered.push({ ticket: t, input: i });
    },
    stop(a) {
      this.stopped.push(a);
    },
  };
}

async function startMockModel() {
  const calls = [];
  const server = createServer((request, response) => {
    let body = "";
    request.on("data", (chunk) => {
      body += chunk.toString("utf8");
    });
    request.on("end", () => {
      let messages = [];
      try {
        messages = JSON.parse(body).messages ?? [];
      } catch {
        /* ignore */
      }
      const system = messages[0]?.content ?? "";
      calls.push({ system: system.slice(0, 40), messages });
      let content;
      if (system.includes("Router")) {
        const user = messages.at(-1)?.content ?? "{}";
        let threads = [];
        try {
          threads = JSON.parse(user).threads ?? [];
        } catch {
          threads = [];
        }
        content = JSON.stringify({
          decisions: threads.map((item) => ({
            threadId: item.view?.threadId ?? item.threadId,
            kind: "accept",
            strength: "explicit",
            scope: "ticket",
            reason: "demo",
            rules: [],
          })),
        });
      } else if (system.includes("external Watchdog")) {
        content = '{"action":"ok","reason":"progressing"}';
      } else {
        content = '{"action":"report","status":"ready","summary":"done"}';
      }
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ choices: [{ message: { content } }] }));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  return {
    baseUrl: `http://127.0.0.1:${port}`,
    calls,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

console.log("=== 文章能力逐条现场验证（seed-agent 内核） ===\n");

const mock = await startMockModel();
const clock = new FakeClock();
const executor = captureExecutor();
let runtime;
const batches = [];
const router = new RouterSession({
  client: new OpenAIClient({
    baseUrl: mock.baseUrl,
    apiKey: "demo",
    model: "mock",
    timeoutMs: 5000,
  }),
  state: () => runtime.engine.state,
  onBatch: (batch) => batches.push(batch),
});
runtime = Runtime.build({
  assessor: router,
  executor,
  config: { dbPath: ":memory:", policy, slots: 2 },
  clock,
});

// §2.1 Router 批处理
runtime.engine.ingest(trigger("trg-1", { threadIds: ["thr-A"], channelIds: ["local:A"], at: 1 }));
runtime.engine.ingest(trigger("trg-2", { threadIds: ["thr-B"], channelIds: ["local:B"], at: 2 }));
await runtime.tickUntilIdle();
check(
  "§2.1 Router 把同轮多个 Thread 合并为一次模型调用",
  mock.calls.length === 1 && batches.at(-1)?.threads === 2,
  `modelCalls=${mock.calls.length}, batch=${JSON.stringify(batches.at(-1))}`,
);
check(
  "§2.1 Router 决策后创建两个隔离工单",
  Object.keys(runtime.engine.state.tickets).length === 2,
  `tickets=${Object.keys(runtime.engine.state.tickets).length}`,
);

// §2.2 / §3.2 订阅直通
const callsBefore = mock.calls.length;
runtime.engine.ingest(
  trigger("trg-3", { threadIds: ["thr-A"], channelIds: ["local:A"], text: "后续补充", at: 3 }),
);
await runtime.tickUntilIdle();
check(
  "§3.2 已订阅 Thread 的后续事件直通 Worker（不再调用 Router）",
  runtime.engine.state.dispositions["trg-3"] === "fanned_out" && mock.calls.length === callsBefore,
  `disposition=${runtime.engine.state.dispositions["trg-3"]}, modelCalls=${mock.calls.length}`,
);
check(
  "§2.2 事件作为 input 投递给 Worker",
  executor.delivered.some((item) => item.input.ref === "trg-3"),
  `delivered=${executor.delivered.map((item) => item.input.ref).join(",")}`,
);

// §3.2 同一 Thread 多 Worker
const ticketB = Object.values(runtime.engine.state.tickets).find((item) =>
  item.threadIds.includes("thr-B"),
);
runtime.store.appendAll([
  ev.subscriptionAdded({ ticketId: ticketB.id, threadId: "thr-A", kind: "context" }, clock.now()),
]);
runtime.engine.ingest(
  trigger("trg-4", { threadIds: ["thr-A"], channelIds: ["local:A"], text: "共享环境变更", at: 4 }),
);
await runtime.tickUntilIdle();
check(
  "§2.2 同一 Thread 的新事件同时直通多个 Worker",
  executor.delivered.filter((item) => item.input.ref === "trg-4").length === 2,
  `receivers=${executor.delivered.filter((item) => item.input.ref === "trg-4").length}`,
);

// §3.1 Fast Path Gate
runtime.engine.ingest(
  trigger("trg-bot", { actor: "bot", threadIds: ["thr-C"], channelIds: ["local:C"], at: 5 }),
);
check(
  "§3.1 程序层 Gate 在调用模型前过滤非白名单发送者",
  runtime.engine.state.dispositions["trg-bot"] === "filtered",
  `disposition=${runtime.engine.state.dispositions["trg-bot"]}`,
);

// §3.3 Inline & Spill + 链式召回
const longTrigger = trigger("trg-long", {
  text: `方案细节：${"x".repeat(5000)}`,
  threadIds: ["thr-A"],
});
const view = buildView({
  threadId: "thr-A",
  triggers: [longTrigger],
  history: [trigger("trg-1")],
  tickets: [],
  policy,
});
const recalled = recall(runtime.engine.state, "thread", "thr-A");
check(
  "§3.3 超预算内容被截断并保留 recall 句柄",
  view.triggers.at(-1)?.text.truncated === true && recalled.found,
  `truncated=${view.triggers.at(-1)?.text.truncated}, handles=${view.handles.length}`,
);
check(
  "§3.3 链式召回返回下一跳 ID",
  recalled.handles.some((handle) => handle.kind === "ticket" || handle.kind === "trigger"),
  `handles=${JSON.stringify(recalled.handles.slice(0, 3))}`,
);

// §3.4 投机执行：后台尝试，有价值才交付
const specDir = mkdtempSync(join(tmpdir(), "seed-demo-spec-"));
const specDelivered = [];
const specModel = {
  async complete(messages) {
    const all = messages.map((message) => message.content).join("\n");
    return all.includes("404")
      ? '{"action":"report","status":"ready","summary":"确认路由缺失，已补上简单修复"}'
      : '{"action":"report","status":"blocked","summary":"未复现，保持安静"}';
  },
};
const speculator = new Speculator({
  runner: reactSpeculationRunner({
    model: specModel,
    root: specDir,
    clock,
    ticket: ticket(),
    maxSteps: 2,
  }),
  deliver: (_candidate, verdict) => {
    specDelivered.push(verdict.summary);
  },
  options: { sources: ["feishu"], timeoutMs: 5000 },
});
const valuable = await speculator.run({
  id: "trg-spec-good",
  source: "feishu",
  text: "群友反馈 404，帮忙看看",
  channelIds: ["fs:oc_1"],
});
const noise = await speculator.run({
  id: "trg-spec-noise",
  source: "feishu",
  text: "今天天气不错，闲聊一下",
  channelIds: ["fs:oc_1"],
});
check(
  "§3.4 投机执行：有价值才交付，无价值静默丢弃",
  valuable?.delivered === true && noise?.delivered === false && specDelivered.length === 1,
  `delivered=${JSON.stringify(specDelivered)}, noiseDelivered=${noise?.delivered}`,
);
rmSync(specDir, { recursive: true, force: true });

// §2.2 Worker 内 Subagent
let subagentDone = false;
const subagent = subagentTool({
  model: {
    async complete() {
      return '{"action":"report","status":"ready","summary":"子任务完成"}';
    },
  },
  tools: {},
  jobs: new JobRegistry(clock),
  clock,
  ticket: ticket(),
});
const subResult = await subagent.run({ task: "检查 404 根因" }, new AbortController().signal);
subagentDone = subResult.status === "ready";
check("§2.2 Worker 内可创建 Subagent 并拿到结构化报告", subagentDone, JSON.stringify(subResult));

// §4.1 异步 ReAct / 全双工
const jobs = new JobRegistry(clock);
const jobId = jobs.start("slow-command", "tk-demo", () => new Promise(() => undefined));
check(
  "§4.1 start() 立即返回 jobId，不阻塞当前回合",
  jobs.get(jobId)?.state === "running",
  `job=${jobId}, state=${jobs.get(jobId)?.state}`,
);
jobs.stop(jobId);
check("§4.1 stop() 可终止后台任务", jobs.get(jobId)?.state === "stopped", `state=${jobs.get(jobId)?.state}`);

let stepModelCalls = 0;
const inputs = [];
const stepModel = {
  async complete(messages) {
    stepModelCalls += 1;
    if (stepModelCalls === 1) {
      return '{"action":"tool","tool":"kick","args":{}}';
    }
    const seen = messages.map((message) => message.content).join("\n");
    return seen.includes("new input: 改成方案 B")
      ? '{"action":"report","status":"ready","summary":"已按新输入调整"}'
      : '{"action":"report","status":"failed","summary":"没看到新输入"}';
  },
};
const stepLoop = new ReactLoop({
  model: stepModel,
  tools: {
    kick: {
      run: async () => {
        inputs.push("改成方案 B");
        return "queued";
      },
    },
  },
  jobs: new JobRegistry(clock),
  clock,
  nextInputs: () => inputs.splice(0),
});
const stepReport = await stepLoop.run(ticket(), [trigger("trg-step")]);
check(
  "§4.1 全双工：回合中的新输入在下一推理步被处理",
  stepReport.status === "ready",
  `status=${stepReport.status}, steps=${stepModelCalls}`,
);

// §4.2 多信道
const compact = compactForIm(`## 结论\n**完成** ${"很长的说明".repeat(30)}`);
check("§4.2 IM 信道压缩到 ≤100 字并去掉 Markdown", compact.length <= 101 && !compact.includes("**"), `len=${compact.length}`);
const structured = structureForAsync("修复完成");
check("§4.2 异步信道使用结构化交付", structured.includes("### 结论"), "structureForAsync");
const outDir = mkdtempSync(join(tmpdir(), "seed-demo-out-"));
const docs = new DocsChannel(join(outDir, "docs"), clock);
const mail = new EmailDraftChannel(join(outDir, "mail"), clock);
await docs.send({ id: "docs:demo", threadId: "", address: "docs:demo" }, "## 更新\n内容");
await mail.send({ id: "mailto:a@b.c", threadId: "", address: "mailto:a@b.c" }, "会议改期\n周三下午");
const docFiles = readdirSync(join(outDir, "docs"));
const mailFiles = readdirSync(join(outDir, "mail"));
check(
  "§4.2 文档/邮件草稿信道落盘",
  docFiles.length === 1 && mailFiles.length === 1,
  `${docFiles[0]} / ${mailFiles[0]}`,
);
check(
  "§4.2 邮件草稿含 To/Subject/正文",
  readFileSync(join(outDir, "mail", mailFiles[0]), "utf8").includes("Subject: 会议改期"),
  "eml headers",
);
rmSync(outDir, { recursive: true, force: true });

// §5.1 计算与状态分离
const dbDir = mkdtempSync(join(tmpdir(), "seed-demo-db-"));
const dbPath = join(dbDir, "state.db");
const first = Runtime.build({
  assessor: { assess: () => accept },
  executor: captureExecutor(),
  config: { dbPath, policy, slots: 1 },
  clock: new FakeClock(),
});
first.engine.ingest(trigger("trg-persist"));
await first.tickUntilIdle();
const hashBefore = first.store.replayHash();
first.close();
const reopened = new SqliteStore(dbPath);
const hashAfter = reopened.replayHash();
check(
  "§5.1 状态入库：重启后回放哈希一致",
  hashBefore === hashAfter && Object.keys(reopened.state().triggers).length === 1,
  `hash=${hashBefore.slice(0, 12)}, triggers=${Object.keys(reopened.state().triggers).length}`,
);
reopened.close();
rmSync(dbDir, { recursive: true, force: true });

// §5.2 端侧 HTTP daemon
const daemonDir = mkdtempSync(join(tmpdir(), "seed-demo-daemon-"));
const daemon = await startHttpDaemon({ root: daemonDir, clock: new FakeClock() });
const transport = new HttpTransport({ url: `http://127.0.0.1:${daemon.port}`, pollMs: 10 });
let resolveReport;
const reportPromise = new Promise((resolve) => {
  resolveReport = resolve;
});
const remote = new RemoteExecutor({
  transport,
  clock: new FakeClock(),
  report: (report) => resolveReport(report),
  worker: {
    file: process.execPath,
    args: ["-e", 'console.log(JSON.stringify({status:"ready",summary:"edge exec ok"}));process.exit(0)'],
  },
});
await remote.launch(assignment(), ticket());
const remoteReport = await Promise.race([
  reportPromise,
  new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 10000)),
]);
check(
  "§5.2 跨进程 HTTP daemon 执行并异步回报",
  remoteReport.status === "ready",
  `status=${remoteReport.status}, summary=${remoteReport.summary}`,
);
await remote.stop(assignment());
transport.close();
await daemon.close();
try {
  rmSync(daemonDir, { recursive: true, force: true });
} catch {
  // Windows 上 worker 退出与目录删除可能竞争；演示不关心临时目录残留。
}

// §6 Watchdog
const wdClock = new FakeClock();
const wdRuntime = Runtime.build({
  assessor: { assess: () => accept },
  executor: captureExecutor(),
  config: { dbPath: ":memory:", policy, slots: 1 },
  clock: wdClock,
});
wdRuntime.engine.ingest(trigger("trg-watch"));
await wdRuntime.tickUntilIdle();
wdClock.advance(2000);
const watchdog = new Watchdog({ clock: wdClock, staleSeconds: 10 });
const findings = watchdog.findings(wdRuntime.engine.state);
check(
  "§6 Watchdog 用确定性判据发现停滞",
  findings.some((finding) => finding.kind === "stalled"),
  `findings=${findings.map((finding) => finding.kind).join(",")}`,
);
const answer = await watchdog.ask("为什么这个工单没动静？", wdRuntime.engine.state);
check("§6 Watchdog 可被自然语言询问", answer.includes("open 工单"), answer.split("\n")[0]);
const controller = new WatchdogController(wdRuntime.engine);
const changed = controller.applyPolicy(
  buildPolicy(
    [{ source: "local", actor: "*", allow: true, strength: "explicit", note: "online" }],
    "auto",
    [["local", "*"]],
  ),
);
check(
  "§6 可在线修改准入策略（policy.changed）",
  changed.at(-1)?.type === "policy.changed",
  `event=${changed.at(-1)?.type}`,
);
wdRuntime.close();

console.log("\n[§3.4] 投机执行：内核 Speculator + host speculate()/speculationSources 均已接入；host 需 DSH runtime。");

await mock.close();
runtime.close();

console.log(`\n=== 结果：${passed} 项通过，${failed} 项失败 ===`);
process.exitCode = failed === 0 ? 0 : 1;