import assert from "node:assert/strict";
import { mkdtempSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import type { Report } from "../src/domain.ts";
import { LocalExecutor } from "../src/executor/local.ts";
import * as h from "./helpers.ts";

function workspace(): { root: string; cleanup: () => Promise<void> } {
  const root = mkdtempSync(join(tmpdir(), "seed-exec-"));
  return {
    root,
    async cleanup() {
      for (let attempt = 0; attempt < 60; attempt += 1) {
        try {
          rmSync(root, { recursive: true, force: true });
          return;
        } catch {
          await new Promise((resolve) => setTimeout(resolve, 20));
        }
      }
    },
  };
}

function onceReport(executor: LocalExecutor, reports: Report[]): Promise<Report> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("report timeout")), 8000);
    const poll = setInterval(() => {
      const found = reports.at(-1);
      if (found) {
        clearInterval(poll);
        clearTimeout(timer);
        resolve(found);
      }
    }, 10);
  });
}

test("LocalExecutor：建目录、注入环境变量、回收结构化报告", async () => {
  const dir = workspace();
  const reports: Report[] = [];
  const clock = new FakeClock();
  const script = [
    "const env = process.env;",
    'console.log(JSON.stringify({ status: "ready", summary: `ticket=${env.DSH_SUPERAGENT_TICKET} scope=${env.DSH_SUPERAGENT_SCOPE}` }));',
  ].join("\n");
  const executor = new LocalExecutor({
    root: dir.root,
    worker: { file: process.execPath, args: ["-e", script] },
    clock,
    report: (report) => reports.push(report),
  });

  const assignment = h.assignment("as-1", { ticketId: "tk-1" });
  const ticket = h.ticket("tk-1", { shortName: "t-000001" });
  await executor.launch(assignment, ticket);
  const report = await onceReport(executor, reports);

  assert.equal(report.status, "ready");
  assert.match(report.summary, /ticket=tk-1/);
  assert.match(report.summary, /scope=ticket/);
  assert.equal(report.assignmentId, "as-1");
  assert.equal(report.at, clock.now());
  assert.ok(readdirSync(dir.root).includes("t-000001"));
  await dir.cleanup();
});

test("LocalExecutor：deliver 把输入写进 worker stdin", async () => {
  const dir = workspace();
  const reports: Report[] = [];
  const script = [
    'process.stdin.setEncoding("utf8");',
    "let buffer = '';",
    'process.stdin.on("data", (chunk) => { buffer += chunk; const lines = buffer.split("\\n"); buffer = lines.pop(); ' +
      'for (const line of lines) { if (!line.trim()) continue; console.log(JSON.stringify({ status: "ready", summary: line })); } });',
  ].join("\n");
  const executor = new LocalExecutor({
    root: dir.root,
    worker: { file: process.execPath, args: ["-e", script] },
    clock: new FakeClock(),
    report: (report) => reports.push(report),
  });

  const assignment = h.assignment("as-1", { ticketId: "tk-1" });
  const ticket = h.ticket("tk-1", { shortName: "t-000002" });
  await executor.launch(assignment, ticket);
  await new Promise((resolve) => setTimeout(resolve, 100)); // 等 worker 就绪
  await executor.deliver(ticket, h.input("inp-7", { ticketId: "tk-1" }));

  const deadline = Date.now() + 8000;
  while (reports.length === 0 && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  assert.ok(reports.length >= 1);
  assert.match(reports.at(-1)?.summary ?? "", /inp-7/);

  await executor.stop(assignment);
  await dir.cleanup();
});

test("LocalExecutor：prepare 失败会让 launch 抛错（交给 outbox 重试）", async () => {
  const dir = workspace();
  const executor = new LocalExecutor({
    root: dir.root,
    prepare: { file: process.execPath, args: ["-e", "process.exit(3)"] },
    worker: { file: process.execPath, args: ["-e", "process.exit(0)"] },
    clock: new FakeClock(),
    report: () => undefined,
  });
  await assert.rejects(executor.launch(h.assignment(), h.ticket()));
  await dir.cleanup();
});