import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { Runtime } from "../src/runtime.ts";
import { createUiServer, type UiServer } from "../src/ui/server.ts";
import { RecordingExecutor, ScriptedAssessor } from "./fakes.ts";
import * as h from "./helpers.ts";

async function setup(token?: string): Promise<{ rt: Runtime; server: UiServer; executor: RecordingExecutor }> {
  const clock = new FakeClock();
  const executor = new RecordingExecutor();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([h.accept(), h.accept(), h.accept()]),
    executor,
    config: { policy: h.policy(), slots: 2 },
    clock,
  });
  const server = await createUiServer({ runtime: rt, port: 0, ...(token ? { token } : {}) });
  return { rt, server, executor };
}

async function getJson(url: string): Promise<{ status: number; body: unknown }> {
  const response = await fetch(url);
  return { status: response.status, body: await response.json() };
}

test("UI 服务：静态资源与 /api/state", async () => {
  const { rt, server } = await setup();
  try {
    const page = await fetch(server.url);
    assert.equal(page.status, 200);
    const html = await page.text();
    assert.match(html, /seed-agent/);
    assert.match(html, /app\.css/);

    const css = await fetch(`${server.url}app.css`);
    assert.equal(css.status, 200);
    assert.match(css.headers.get("content-type") ?? "", /text\/css/);

    const { status, body } = await getJson(`${server.url}api/state`);
    assert.equal(status, 200);
    const ui = body as { counts: { total: number }; paused: boolean };
    assert.equal(ui.paused, false);
    assert.equal(ui.counts.total, 0);
  } finally {
    await server.close();
    rt.close();
  }
});

test("UI 服务：pause/resume/reply 命令会驱动引擎", async () => {
  const { rt, server, executor } = await setup();
  try {
    rt.engine.ingest(h.trigger("trg-1", { text: "写个文件" }));
    await rt.tickUntilIdle();
    const ticketId = Object.keys(rt.engine.state.tickets)[0];
    assert.ok(ticketId);

    const pauseResponse = await fetch(`${server.url}api/command`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ type: "pause" }),
    });
    assert.equal(pauseResponse.status, 200);
    assert.equal(rt.engine.isPaused, true);

    await fetch(`${server.url}api/command`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ type: "resume" }),
    });
    assert.equal(rt.engine.isPaused, false);

    const reply = await fetch(`${server.url}api/command`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ type: "reply", ticketId, text: "请补一个测试" }),
    });
    assert.equal(reply.status, 200);
    assert.ok(executor.delivered.length >= 1);

    const view = await getJson(`${server.url}api/tickets/${ticketId}`);
    assert.equal(view.status, 200);
    const timeline = (view.body as { timeline: { kind: string; text: string }[] }).timeline;
    assert.ok(timeline.some((item) => item.kind === "input" && item.text.includes("请补一个测试")));

    const bad = await fetch(`${server.url}api/command`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ type: "nope" }),
    });
    assert.equal(bad.status, 400);
  } finally {
    await server.close();
    rt.close();
  }
});

test("UI 服务：token 保护 API，静态资源仍可访问", async () => {
  const { rt, server } = await setup("secret");
  try {
    const page = await fetch(server.url);
    assert.equal(page.status, 200);
    const denied = await fetch(`${server.url}api/state`);
    assert.equal(denied.status, 401);
    const allowed = await fetch(`${server.url}api/state?token=secret`);
    assert.equal(allowed.status, 200);
  } finally {
    await server.close();
    rt.close();
  }
});

test("UI 服务：SSE 首次推送包含状态", async () => {
  const { rt, server } = await setup();
  const controller = new AbortController();
  try {
    const response = await fetch(`${server.url}api/stream`, { signal: controller.signal });
    assert.equal(response.status, 200);
    assert.match(response.headers.get("content-type") ?? "", /text\/event-stream/);
    const reader = response.body?.getReader();
    assert.ok(reader);
    const chunk = await reader.read();
    const text = Buffer.from(chunk.value ?? new Uint8Array()).toString("utf8");
    assert.match(text, /^data: \{/);
    assert.match(text, /"counts"/);
  } finally {
    controller.abort();
    await server.close();
    rt.close();
  }
});

test("UI 服务：未知路径与未知工单返回 404", async () => {
  const { rt, server } = await setup();
  try {
    const missing = await fetch(`${server.url}nope`);
    assert.equal(missing.status, 404);
    const ticket = await fetch(`${server.url}api/tickets/tk-nope`);
    assert.equal(ticket.status, 404);
  } finally {
    await server.close();
    rt.close();
  }
});