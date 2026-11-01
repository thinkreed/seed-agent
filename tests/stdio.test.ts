import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { StdioTransport } from "../src/executor/stdio.ts";
import { RemoteExecutor } from "../src/executor/remote.ts";
import { ScriptedAssessor } from "../src/fakes.ts";
import { Runtime } from "../src/runtime.ts";
import * as h from "./helpers.ts";

const REPO = join(import.meta.dirname, "..");

async function waitFor(predicate: () => boolean, timeoutMs = 10000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error("timeout");
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

function workspace(): { root: string; cleanup: () => Promise<void> } {
  const root = mkdtempSync(join(tmpdir(), "seed-stdio-"));
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

test("stdio transport：daemon 独立进程执行并把报告推回来", async () => {
  const dir = workspace();
  const clock = new FakeClock();
  const transport = new StdioTransport({
    command: process.execPath,
    args: [join(REPO, "src", "daemon", "main.ts")],
    cwd: REPO,
    env: { SEED_DAEMON_ROOT: dir.root },
  });

  const executor = new RemoteExecutor({
    transport,
    clock,
    report: (report) => runtime.engine.report(report),
    worker: {
      file: process.execPath,
      args: ["-e", 'console.log(JSON.stringify({ status: "ready", summary: "跨进程完成" }));'],
    },
  });

  const runtime = Runtime.build({
    assessor: new ScriptedAssessor([h.accept()]),
    executor,
    config: { policy: h.policy(), slots: 1 },
    clock,
  });

  runtime.engine.ingest(h.trigger());
  await runtime.tickUntilIdle();
  await waitFor(() => Object.values(runtime.engine.state.tickets)[0]?.state === "ended");

  const ticket = Object.values(runtime.engine.state.tickets)[0];
  assert.ok(ticket);
  const reports = runtime.engine.state.reports[ticket.id] ?? [];
  assert.equal(reports.at(-1)?.status, "ready");

  transport.close();
  runtime.close();
  await dir.cleanup();
});