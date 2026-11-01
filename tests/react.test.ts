import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import type { Report } from "../src/domain.ts";
import { JobRegistry } from "../src/jobs.ts";
import type { ModelClient, ModelMessage } from "../src/model.ts";
import { parseAction, ReactLoop } from "../src/react.ts";
import * as h from "./helpers.ts";

class ScriptedModel implements ModelClient {
  readonly calls: number[] = [];
  private readonly replies: string[];

  constructor(replies: string[]) {
    this.replies = [...replies];
  }

  async complete(_messages: readonly ModelMessage[]): Promise<string> {
    this.calls.push(this.calls.length);
    return this.replies.shift() ?? '{"action":"report","status":"failed","summary":"no more script"}';
  }
}

function setup(replies: string[], tools: Parameters<typeof ReactLoop.prototype.constructor>[0]["tools"]) {
  const clock = new FakeClock();
  const jobs = new JobRegistry(clock);
  const reports: Report[] = [];
  const loop = new ReactLoop({
    model: new ScriptedModel(replies),
    tools,
    jobs,
    clock,
    report: (report) => reports.push(report),
  });
  return { loop, clock, jobs, reports };
}

test("tool 动作 -> observation -> report", async () => {
  const { loop, reports } = setup(
    [
      '{"action":"tool","tool":"read","args":{"path":"a.txt"}}',
      '{"action":"report","status":"ready","summary":"读到 a.txt"}',
    ],
    {
      read: {
        run: async (args) => ({ path: args.path, content: "hello" }),
      },
    },
  );
  const report = await loop.run(h.ticket(), [h.trigger()]);
  assert.equal(report.status, "ready");
  assert.equal(reports.length, 1);
  assert.match(report.summary, /a\.txt/);
});

test("start 动作启动后台任务，完成通知在后续步骤注入", async () => {
  const { loop, jobs } = setup(
    [
      '{"action":"start","tool":"slow","args":{}}',
      '{"action":"report","status":"waiting","summary":"等后台跑完"}',
    ],
    {
      slow: {
        run: async () => {
          await new Promise((resolve) => setTimeout(resolve, 20));
          return "slow-result";
        },
      },
    },
  );
  const report = await loop.run(h.ticket(), []);
  assert.equal(report.status, "waiting");
  assert.equal(jobs.running().length, 1);
});

test("stop 动作可以终止后台任务", async () => {
  const { loop, jobs } = setup(
    [
      '{"action":"start","tool":"hang","args":{}}',
      '{"action":"stop","jobId":"job-000001"}',
      '{"action":"report","status":"waiting","summary":"已停止"}',
    ],
    {
      hang: {
        run: (signal) =>
          new Promise((_resolve, reject) => {
            signal.addEventListener("abort", () => reject(new Error("aborted")));
          }),
      },
    },
  );
  await loop.run(h.ticket(), []);
  assert.equal(jobs.get("job-000001")?.state, "stopped");
});

test("未知工具只产生 observation，不崩溃", async () => {
  const { loop } = setup(
    ['{"action":"tool","tool":"nope","args":{}}', '{"action":"report","status":"failed","summary":"工具不存在"}'],
    {},
  );
  const report = await loop.run(h.ticket(), []);
  assert.equal(report.status, "failed");
});

test("无法解析的动作：先给修复提示，最终 failed", async () => {
  const { loop } = setup(["I will think about it."], {});
  const report = await loop.run(h.ticket(), []);
  assert.equal(report.status, "failed");
});

test("超过 maxSteps 报 failed", async () => {
  const clock = new FakeClock();
  const loop = new ReactLoop({
    model: new ScriptedModel(Array.from({ length: 10 }, () => '{"action":"tool","tool":"t","args":{}}')),
    tools: { t: { run: async () => "ok" } },
    jobs: new JobRegistry(clock),
    clock,
    maxSteps: 3,
  });
  const report = await loop.run(h.ticket(), []);
  assert.equal(report.status, "failed");
  assert.match(report.summary, /max steps/);
});

test("parseAction：拒绝非法输入", () => {
  assert.equal(parseAction("not json"), null);
  assert.equal(parseAction('{"action":"report","status":"nope"}'), null);
  assert.equal(parseAction('{"action":"tool"}'), null);
  assert.equal(parseAction('{"action":"stop","jobId":""}'), null);
  assert.deepEqual(parseAction('{"action":"stop","jobId":"job-1"}'), { action: "stop", jobId: "job-1" });
});