import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import type { Report } from "../src/domain.ts";
import { JobRegistry } from "../src/jobs.ts";
import type { ModelClient, ModelMessage } from "../src/model.ts";
import { WorkerSession } from "../src/worker.ts";
import * as h from "./helpers.ts";

/** 第一轮慢一点，便于在 turn 进行中投递新消息。 */
class SlowModel implements ModelClient {
  readonly replies: string[];
  readonly seen: number[] = [];

  constructor(replies: string[]) {
    this.replies = [...replies];
  }

  async complete(_messages: readonly ModelMessage[]): Promise<string> {
    this.seen.push(this.seen.length);
    if (this.seen.length === 1) await new Promise((resolve) => setTimeout(resolve, 25));
    return this.replies.shift() ?? '{"action":"report","status":"waiting","summary":"idle"}';
  }
}

test("WorkerSession：turn 进行中投递的消息会被下一轮消费", async () => {
  const clock = new FakeClock();
  const reports: Report[] = [];
  const session = new WorkerSession({
    model: new SlowModel([
      '{"action":"report","status":"waiting","summary":"第一轮结束"}',
      '{"action":"report","status":"ready","summary":"处理了追加消息"}',
    ]),
    tools: {},
    jobs: new JobRegistry(clock),
    clock,
  });

  const ticket = h.ticket();
  const running = session.run(ticket, [h.trigger("trg-1")]);
  // 第一个 turn 还没结束就投递
  await new Promise((resolve) => setTimeout(resolve, 5));
  session.deliver(h.trigger("trg-2", { text: "追加：顺便修下 404" }));
  assert.equal(session.queued, 1);

  const finished = await running;
  assert.equal(finished.length, 2);
  assert.equal(finished[0]?.status, "waiting");
  assert.equal(finished[1]?.status, "ready");
  assert.match(finished[1]?.summary ?? "", /追加消息/);
  void reports;
});

test("WorkerSession：没有追加输入时只跑一轮", async () => {
  const clock = new FakeClock();
  const session = new WorkerSession({
    model: new SlowModel(['{"action":"report","status":"ready","summary":"done"}']),
    tools: {},
    jobs: new JobRegistry(clock),
    clock,
  });
  const reports = await session.run(h.ticket(), [h.trigger()]);
  assert.equal(reports.length, 1);
  assert.equal(session.queued, 0);
});

test("WorkerSession：达到 maxTurns 后停止继续消费", async () => {
  const clock = new FakeClock();
  const session = new WorkerSession({
    model: {
      complete: async () => '{"action":"report","status":"progress","summary":"more"}',
    },
    tools: {},
    jobs: new JobRegistry(clock),
    clock,
    maxTurns: 1,
  });
  session.deliver(h.trigger("trg-a"));
  session.deliver(h.trigger("trg-b"));
  const reports = await session.run(h.ticket(), [h.trigger("trg-0")]);
  assert.equal(reports.length, 1);
  assert.equal(session.queued, 2);
});