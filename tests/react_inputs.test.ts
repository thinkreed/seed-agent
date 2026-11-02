import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import type { Report } from "../src/domain.ts";
import { JobRegistry } from "../src/jobs.ts";
import type { ModelClient, ModelMessage } from "../src/model.ts";
import { WorkerSession } from "../src/worker.ts";
import * as h from "./helpers.ts";

class RecordingModel implements ModelClient {
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

test("全双工：回合中到达的输入在下一个推理步前注入，无需等回合结束", async () => {
  const clock = new FakeClock();
  const jobs = new JobRegistry(clock);
  const model = new RecordingModel([
    '{"action":"tool","tool":"kick","args":{}}',
    '{"action":"report","status":"ready","summary":"已按新输入调整"}',
  ]);
  let session: WorkerSession;
  const tools = {
    kick: {
      description: "simulate new input arriving while a tool runs",
      run: async (): Promise<string> => {
        session.deliver(h.trigger("trg-new", { text: "改为方案 B" }));
        return "queued";
      },
    },
  };
  session = new WorkerSession({ model, tools, jobs, clock });
  const reports: Report[] = await session.run(h.ticket(), [h.trigger()]);
  assert.equal(reports.length, 1, "新输入在回合内消化，不需要额外回合");
  assert.equal(reports[0]?.status, "ready");
  assert.equal(session.queued, 0);
  const secondCall = model.calls[1]?.join("\n") ?? "";
  assert.match(secondCall, /new input: 改为方案 B/);
});