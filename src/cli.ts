/** 命令行入口。
 *
 *   node src/cli.ts           # 端到端演示
 *   node src/cli.ts panel f   # 读取 sqlite 库并打印面板
 */

import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { App } from "./app.ts";
import { loadConfig } from "./config.ts";
import { FakeClock } from "./clock.ts";
import { RecordingChannel } from "./channels/recording.ts";
import type { Decision, Report, Trigger } from "./domain.ts";
import { RemoteExecutor } from "./executor/remote.ts";
import { StdioTransport } from "./executor/stdio.ts";
import { RecordingExecutor, ScriptedAssessor } from "./fakes.ts";
import { SeqIds } from "./ids.ts";
import { render, renderJson } from "./panel.ts";
import { defaultPolicy } from "./policy.ts";
import { Router } from "./router.ts";
import { Runtime } from "./runtime.ts";
import { SqliteStore } from "./store.ts";
import { openAssignment } from "./domain.ts";

function accept(reason = "asked-directly"): Decision {
  return { kind: "accept", strength: "explicit", reason, rules: [], scope: "ticket" };
}

export async function demo(): Promise<number> {
  const clock = new FakeClock();
  const assessor = new ScriptedAssessor([accept()]);
  const executor = new RecordingExecutor();
  const channel = new RecordingChannel();
  const runtime = Runtime.build({
    assessor,
    executor,
    config: { dbPath: ":memory:", slots: 2, policy: defaultPolicy(), channels: channel },
    clock,
    ids: new SeqIds(),
  });
  const router = new Router({ store: runtime.store, clock, effects: runtime.engine.effects });

  const trigger: Trigger = {
    id: "trg-000001",
    source: "local",
    actor: "alice",
    text: "修复登录页的 500 错误",
    threadIds: ["thr-local-1"],
    channelIds: ["chan-local-1"],
    at: 0,
  };

  runtime.engine.ingest(trigger);
  await runtime.tickUntilIdle();

  const state = runtime.engine.state;
  const ticket = Object.values(state.tickets)[0];
  if (!ticket) throw new Error("demo expected one ticket");
  const assignment = openAssignment(state, ticket.id);
  if (!assignment) throw new Error("demo expected an assignment");

  const report: Report = {
    ticketId: ticket.id,
    assignmentId: assignment.id,
    status: "ready",
    summary: "修复完成，已提 PR",
    at: clock.now(),
  };
  runtime.engine.report(report);
  await runtime.tickUntilIdle();
  router.queueReplies();
  await runtime.tickUntilIdle();

  console.log(`events       : ${runtime.store.lastSeq()}`);
  console.log(`tickets      : ${Object.keys(runtime.engine.state.tickets).length}`);
  console.log(`ticket state : ${Object.values(runtime.engine.state.tickets)[0]?.state}`);
  console.log(`replay hash  : ${runtime.store.replayHash().slice(0, 16)}`);
  console.log(`launched     : ${executor.launched.map((item) => item.assignment.id).join(", ")}`);
  console.log(`replies      : ${channel.sent.map((item) => item.text).join(" | ") || "(none)"}`);
  console.log("--- panel ---");
  console.log(render(runtime.engine.state));
  runtime.close();
  return 0;
}

export function showPanel(path: string, asJson = false): number {
  const store = new SqliteStore(path);
  console.log(asJson ? renderJson(store.state()) : render(store.state()));
  store.close();
  return 0;
}

/** 计算与执行分离的演示：daemon 作为独立进程执行，报告跨进程回流。 */
export async function remoteDemo(): Promise<number> {
  const clock = new FakeClock();
  const root = mkdtempSync(join(tmpdir(), "seed-demo-"));
  const transport = new StdioTransport({
    command: process.execPath,
    args: [join(import.meta.dirname, "daemon", "main.ts")],
    cwd: join(import.meta.dirname, ".."),
    env: { SEED_DAEMON_ROOT: root },
  });
  const executor = new RemoteExecutor({
    transport,
    clock,
    report: (report) => runtime.engine.report(report),
    worker: {
      file: process.execPath,
      args: ["-e", 'console.log(JSON.stringify({ status: "ready", summary: "daemon 执行完成" }));'],
    },
  });
  const runtime = Runtime.build({
    assessor: new ScriptedAssessor([accept()]),
    executor,
    config: { dbPath: ":memory:", slots: 1, policy: defaultPolicy() },
    clock,
    ids: new SeqIds(),
  });

  runtime.engine.ingest({
    id: "trg-remote-1",
    source: "local",
    actor: "alice",
    text: "在远端执行环境里跑一次任务",
    threadIds: ["thr-remote-1"],
    channelIds: ["chan-remote-1"],
    at: 0,
  });
  await runtime.tickUntilIdle();
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (Object.values(runtime.engine.state.tickets)[0]?.state === "ended") break;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }

  const ticket = Object.values(runtime.engine.state.tickets)[0];
  console.log(`daemon pid   : ${transport.pid}`);
  console.log(`ticket       : ${ticket?.shortName} -> ${ticket?.state}`);
  console.log(`report       : ${ticket ? (runtime.engine.state.reports[ticket.id]?.at(-1)?.summary ?? "") : ""}`);
  console.log(`events       : ${runtime.store.lastSeq()}`);
  transport.close();
  runtime.close();
  rmSync(root, { recursive: true, force: true });
  return 0;
}

/** 真实运行：配置驱动，接真实模型与渠道。 */
export async function runApp(configPath: string | undefined, once: boolean): Promise<number> {
  const config = loadConfig(configPath);
  const app = App.create({ config });
  if (once) {
    await app.runOnce();
    console.log(render(app.runtime.engine.state));
    app.stop();
    return 0;
  }
  process.on("SIGINT", () => app.stop());
  await app.run();
  return 0;
}

const [, , command = "demo", arg, flag] = process.argv;
const exitCode =
  command === "demo"
    ? await demo()
    : command === "remote"
      ? await remoteDemo()
      : command === "run"
        ? await runApp(arg, flag === "--once")
        : command === "panel"
          ? showPanel(arg ?? "seed.db", flag === "--json")
          : 2;
process.exitCode = exitCode;