import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { DaemonAgent } from "../src/daemon/agent.ts";
import type { DaemonEvent, DaemonRequest, DaemonResponse, Transport } from "../src/executor/protocol.ts";
import { RemoteExecutor } from "../src/executor/remote.ts";
import { RecordingExecutor, ScriptedAssessor } from "./fakes.ts";
import { Runtime } from "../src/runtime.ts";
import * as h from "./helpers.ts";

async function waitFor(predicate: () => boolean, timeoutMs = 8000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error("timeout");
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

function workspace(): { root: string; cleanup: () => Promise<void> } {
  const root = mkdtempSync(join(tmpdir(), "seed-daemon-"));
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

function memoryTransport(handle: (request: DaemonRequest) => Promise<DaemonResponse>): {
  transport: Transport;
  emit: (event: DaemonEvent) => void;
  down: boolean;
} {
  let handler: (event: DaemonEvent) => void = () => undefined;
  const state = {
    down: false,
    emit: (event: DaemonEvent) => handler(event),
    transport: {
      send: async (request: DaemonRequest) => {
        if (state.down) throw new Error("daemon offline");
        return handle(request);
      },
      onEvent: (next: (event: DaemonEvent) => void) => {
        handler = next;
      },
      close: () => undefined,
    } satisfies Transport,
  };
  return state;
}

test("远端执行器 + 本地 daemon：报告异步回流，工单结束", async () => {
  const dir = workspace();
  const clock = new FakeClock();
  const script =
    'console.log(JSON.stringify({ status: "ready", summary: "daemon 执行完成" }));';

  let agent: DaemonAgent | undefined;
  const bridge = memoryTransport(async (request) => {
    if (!agent) throw new Error("agent not ready");
    return agent.handle(request);
  });
  agent = new DaemonAgent({ clock, root: dir.root, emit: (event) => bridge.emit(event) });

  const executor = new RemoteExecutor({
    transport: bridge.transport,
    clock,
    report: (report) => runtime.engine.report(report),
    worker: { file: process.execPath, args: ["-e", script] },
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
  runtime.close();
  await dir.cleanup();
});

test("daemon 离线：launch 走 outbox 退避，恢复后可以启动", async () => {
  const dir = workspace();
  const clock = new FakeClock();
  const bridge = memoryTransport(async () => ({ id: "x", ok: true }));
  bridge.down = true;

  const executor = new RemoteExecutor({
    transport: bridge.transport,
    clock,
    report: () => undefined,
    worker: { file: process.execPath, args: ["-e", "process.exit(0)"] },
  });
  const runtime = Runtime.build({
    assessor: new ScriptedAssessor([h.accept()]),
    executor,
    config: { policy: h.policy(), slots: 1 },
    clock,
  });

  runtime.engine.ingest(h.trigger());
  await runtime.tickUntilIdle();
  assert.equal(Object.values(runtime.engine.state.assignments)[0]?.state, "pending");

  bridge.down = false;
  clock.advance(2);
  await runtime.tickUntilIdle();
  assert.equal(Object.values(runtime.engine.state.assignments)[0]?.state, "running");
  runtime.close();
  await dir.cleanup();
});

test("DaemonAgent 对未知工单的 deliver 返回错误而不是崩溃", async () => {
  const dir = workspace();
  const agent = new DaemonAgent({
    clock: new FakeClock(),
    root: dir.root,
    emit: () => undefined,
  });
  const response = await agent.handle({
    id: "req-1",
    cmd: "deliver",
    ticketId: "tk-ghost",
    inputId: "inp-1",
    kind: "text",
    ref: "hi",
  });
  assert.equal(response.ok, false);
  await dir.cleanup();
  void RecordingExecutor;
  void RecordingExecutor;
});