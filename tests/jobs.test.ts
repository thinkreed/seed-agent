import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { JobRegistry } from "../src/jobs.ts";

async function waitFor(predicate: () => boolean, timeoutMs = 3000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error("timeout");
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

test("start 立即返回 jobId，完成后有通知与结果", async () => {
  const clock = new FakeClock();
  const jobs = new JobRegistry(clock);
  const id = jobs.start("shell", "tk-1", async () => "done-output");
  assert.equal(id, "job-000001");
  assert.equal(jobs.get(id)?.state, "running");

  await waitFor(() => jobs.get(id)?.state === "done");
  assert.equal(jobs.get(id)?.result, "done-output");
  const notices = jobs.drainNotices();
  assert.equal(notices.length, 1);
  assert.equal(notices[0]?.jobId, id);
  assert.deepEqual(jobs.drainNotices(), []);
});

test("失败任务记录 error 并通知", async () => {
  const jobs = new JobRegistry(new FakeClock());
  const id = jobs.start("shell", "tk-1", async () => {
    throw new Error("boom");
  });
  await waitFor(() => jobs.get(id)?.state === "failed");
  assert.match(jobs.get(id)?.error ?? "", /boom/);
});

test("stop 协作取消：任务收到 abort 信号", async () => {
  const jobs = new JobRegistry(new FakeClock());
  let aborted = false;
  const id = jobs.start(
    "shell",
    "tk-1",
    (signal) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => {
          aborted = true;
          reject(new Error("aborted"));
        });
      }),
  );
  assert.equal(jobs.get(id)?.state, "running");
  await new Promise((resolve) => setTimeout(resolve, 10)); // 等 run 真正开始
  assert.equal(jobs.stop(id), true);
  await waitFor(() => aborted);
  assert.equal(jobs.get(id)?.state, "stopped");
});

test("tick 把超时任务判死", async () => {
  const clock = new FakeClock();
  const jobs = new JobRegistry(clock, { maxRunSeconds: 10 });
  const id = jobs.start("shell", "tk-1", () => new Promise(() => undefined));
  clock.advance(10);
  jobs.tick();
  assert.equal(jobs.get(id)?.state, "stopped");
  assert.equal(jobs.get(id)?.error, "deadline");
});

test("running 只列进行中的任务", async () => {
  const jobs = new JobRegistry(new FakeClock());
  jobs.start("a", "tk-1", async () => 1);
  jobs.start("b", "tk-1", () => new Promise(() => undefined));
  await waitFor(() => jobs.running().length === 1);
  assert.equal(jobs.running()[0]?.kind, "b");
});