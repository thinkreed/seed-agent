import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import type { Report } from "../src/domain.ts";
import { JobRegistry } from "../src/jobs.ts";
import type { ModelClient, ModelMessage } from "../src/model.ts";
import { WorkerSession } from "../src/worker.ts";
import * as h from "./helpers.ts";

class ScriptedModel implements ModelClient {
  readonly calls: ModelMessage[][] = [];
  private readonly replies: string[];

  constructor(replies: string[]) {
    this.replies = [...replies];
  }

  async complete(messages: readonly ModelMessage[]): Promise<string> {
    this.calls.push([...messages]);
    return this.replies.shift() ?? '{"action":"report","status":"waiting","summary":"idle"}';
  }
}

test("后台任务完成后作为新输入回到同一 Worker 会话（文章 §4.1）", async () => {
  const clock = new FakeClock();
  const jobs = new JobRegistry(clock);
  let release!: () => void;
  const jobGate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const tools = {
    slow: {
      description: "slow background tool",
      run: async (): Promise<string> => {
        await jobGate;
        return "slow-done";
      },
    },
  };
  const model = new ScriptedModel([
    '{"action":"start","tool":"slow","args":{}}',
    '{"action":"report","status":"progress","summary":"后台任务已启动"}',
    '{"action":"report","status":"ready","summary":"已消化后台结果"}',
  ]);
  const session = new WorkerSession({ model, tools, jobs, clock });
  const running = session.run(h.ticket(), [h.trigger("trg-1")]);

  // 等 start() 真正进入 JobRegistry，再放行任务完成。
  for (let i = 0; i < 100 && jobs.runningFor("tk-1").length === 0; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  assert.equal(jobs.runningFor("tk-1").length, 1);
  release();

  const reports: Report[] = await running;
  assert.equal(reports.length, 2);
  assert.equal(reports[0]?.status, "progress");
  assert.equal(reports[1]?.status, "ready");
  const lastCall = model.calls.at(-1)?.map((message) => message.content).join("\n") ?? "";
  assert.match(lastCall, /后台任务 job-000001 done/);
  assert.match(lastCall, /slow-done/);
});

test("没有后台任务时 WorkerSession 不会空等", async () => {
  const clock = new FakeClock();
  const session = new WorkerSession({
    model: new ScriptedModel(['{"action":"report","status":"ready","summary":"done"}']),
    tools: {},
    jobs: new JobRegistry(clock),
    clock,
  });
  const reports = await session.run(h.ticket(), [h.trigger()]);
  assert.equal(reports.length, 1);
  assert.equal(session.queued, 0);
});