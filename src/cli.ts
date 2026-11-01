/** 命令行入口。
 *
 *   node src/cli.ts           # 端到端演示
 *   node src/cli.ts panel f   # 读取 sqlite 库并打印面板
 */

import { FakeClock } from "./clock.ts";
import type { Decision, Report, Trigger } from "./domain.ts";
import { RecordingExecutor, ScriptedAssessor } from "./fakes.ts";
import { SeqIds } from "./ids.ts";
import { render } from "./panel.ts";
import { defaultPolicy } from "./policy.ts";
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
  const runtime = Runtime.build({
    assessor,
    executor,
    config: { dbPath: ":memory:", slots: 2, policy: defaultPolicy() },
    clock,
    ids: new SeqIds(),
  });

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

  console.log(`events       : ${runtime.store.lastSeq()}`);
  console.log(`tickets      : ${Object.keys(runtime.engine.state.tickets).length}`);
  console.log(`ticket state : ${Object.values(runtime.engine.state.tickets)[0]?.state}`);
  console.log(`replay hash  : ${runtime.store.replayHash().slice(0, 16)}`);
  console.log(`launched     : ${executor.launched.map((item) => item.assignment.id).join(", ")}`);
  console.log("--- panel ---");
  console.log(render(runtime.engine.state));
  runtime.close();
  return 0;
}

export function showPanel(path: string): number {
  const store = new SqliteStore(path);
  console.log(render(store.state()));
  store.close();
  return 0;
}

const [, , command = "demo", arg] = process.argv;
const exitCode =
  command === "demo" ? await demo() : command === "panel" ? showPanel(arg ?? "seed.db") : 2;
process.exitCode = exitCode;