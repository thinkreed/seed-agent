import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { JobRegistry } from "../src/jobs.ts";
import type { ModelClient, ModelMessage } from "../src/model.ts";
import { ReactLoop } from "../src/react.ts";
import { subagentTool } from "../src/subagent_tool.ts";
import * as h from "./helpers.ts";

class ScriptedModel implements ModelClient {
  readonly calls: string[][] = [];
  private readonly replies: string[];

  constructor(replies: string[]) {
    this.replies = [...replies];
  }

  async complete(messages: readonly ModelMessage[]): Promise<string> {
    this.calls.push(messages.map((message) => message.content));
    return this.replies.shift() ?? '{"action":"report","status":"failed","summary":"no reply"}';
  }
}

test("Worker 内 Subagent：父会话拿到子任务的结构化报告", async () => {
  const clock = new FakeClock();
  const jobs = new JobRegistry(clock);
  const model = new ScriptedModel([
    '{"action":"tool","tool":"spawn_subagent","args":{"task":"检查 404 根因"}}',
    '{"action":"report","status":"ready","summary":"子任务确认是路由缺失"}',
    '{"action":"report","status":"ready","summary":"父任务汇总：已修复"}',
  ]);
  const baseTools = {
    echo: { description: "echo", run: async (args: Record<string, unknown>) => args },
  };
  const spawn = subagentTool({ model, tools: baseTools, jobs, clock, ticket: h.ticket() });
  const parent = new ReactLoop({
    model,
    tools: { ...baseTools, spawn_subagent: spawn },
    jobs,
    clock,
    maxSteps: 4,
  });

  const report = await parent.run(h.ticket(), [h.trigger()]);
  assert.equal(report.status, "ready");
  assert.match(report.summary, /父任务汇总/);
  assert.equal(model.calls.length, 3, "父 -> 子 -> 父");
  const parentThirdCall = model.calls.at(-1)?.join("\n") ?? "";
  assert.match(parentThirdCall, /子任务确认是路由缺失/);
});

test("Subagent 工具拒绝空任务", async () => {
  const clock = new FakeClock();
  const tool = subagentTool({
    model: new ScriptedModel([]),
    tools: {},
    jobs: new JobRegistry(clock),
    clock,
    ticket: h.ticket(),
  });
  const result = await tool.run({ task: "  " }, new AbortController().signal);
  assert.deepEqual(result, { error: "task required" });
});