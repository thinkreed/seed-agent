import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { startHttpDaemon } from "../src/daemon/http.ts";
import { HttpTransport } from "../src/executor/http.ts";
import { RemoteExecutor } from "../src/executor/remote.ts";
import type { Report } from "../src/domain.ts";
import * as h from "./helpers.ts";

test("HTTP daemon：跨进程/跨网络执行并异步回流报告", async () => {
  const root = mkdtempSync(join(tmpdir(), "seed-http-daemon-"));
  const clock = new FakeClock();
  const daemon = await startHttpDaemon({ root, clock });
  const transport = new HttpTransport({ url: `http://127.0.0.1:${daemon.port}`, pollMs: 10 });
  try {
    let resolveReport!: (report: Report) => void;
    const received = new Promise<Report>((resolve) => {
      resolveReport = resolve;
    });
    const executor = new RemoteExecutor({
      transport,
      clock,
      report: (report) => resolveReport(report),
      worker: {
        file: process.execPath,
        args: ["-e", 'console.log(JSON.stringify({status:"ready",summary:"http done"}));process.exit(0)'],
      },
    });
    const ticket = h.ticket();
    await executor.launch(h.assignment("as-http-1", { ticketId: ticket.id }), ticket);
    const report = await received;
    assert.equal(report.status, "ready");
    assert.match(report.summary, /http done/);
    await executor.stop(h.assignment("as-http-1", { ticketId: ticket.id }));
  } finally {
    transport.close();
    await daemon.close();
    rmSync(root, { recursive: true, force: true });
  }
});

test("HTTP daemon：非本机监听必须带 token", async () => {
  const root = mkdtempSync(join(tmpdir(), "seed-http-token-"));
  try {
    await assert.rejects(
      () => startHttpDaemon({ root, clock: new FakeClock(), host: "0.0.0.0" }),
      /requires SA_DAEMON_TOKEN/,
    );
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("HTTP transport：daemon 从离线恢复时触发 onReconnect", async () => {
  let offline = true;
  let reconnects = 0;
  const transport = new HttpTransport({
    url: "http://daemon.invalid",
    pollMs: 5,
    onReconnect: () => {
      reconnects += 1;
    },
    fetchImpl: (async () => {
      if (offline) throw new Error("offline");
      return new Response(JSON.stringify({ events: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as typeof fetch,
  });
  try {
    await new Promise((resolve) => setTimeout(resolve, 25));
    offline = false;
    await new Promise((resolve) => setTimeout(resolve, 40));
    assert.ok(reconnects >= 1, `expected reconnect, got ${reconnects}`);
  } finally {
    transport.close();
  }
});

test("HTTP daemon：token 不对时拒绝请求", async () => {
  const root = mkdtempSync(join(tmpdir(), "seed-http-auth-"));
  const daemon = await startHttpDaemon({ root, clock: new FakeClock(), token: "secret" });
  const transport = new HttpTransport({
    url: `http://127.0.0.1:${daemon.port}`,
    token: "wrong",
    pollMs: 10,
  });
  try {
    await assert.rejects(() => transport.send({ id: "r1", cmd: "stop", ticketId: "tk" }), /unauthorized/);
  } finally {
    transport.close();
    await daemon.close();
    rmSync(root, { recursive: true, force: true });
  }
});