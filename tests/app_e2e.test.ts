import assert from "node:assert/strict";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { App, AppError } from "../src/app.ts";
import { parseConfig } from "../src/config.ts";

interface MockModel {
  readonly baseUrl: string;
  close(): void;
}

function mockModel(replies: string[]): Promise<MockModel> {
  const queue = [...replies];
  const server: Server = createServer((request, response) => {
    let requestBody = "";
    request.on("data", (chunk: Buffer) => { requestBody += chunk.toString("utf8"); });
    request.on("end", () => {
      // Watchdog 会周期性调用模型但不该消费脚本化回复；按 system prompt 路由。
      const content = requestBody.includes("external Watchdog")
        ? '{"action":"ok","reason":"still making progress"}'
        : queue.shift() ?? '{"action":"report","status":"failed","summary":"no reply"}';
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ choices: [{ message: { content } }] }));
    });
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const port = (server.address() as AddressInfo).port;
      resolve({ baseUrl: `http://127.0.0.1:${port}`, close: () => server.close() });
    });
  });
}

function workspace(): { root: string; cleanup: () => Promise<void> } {
  const root = mkdtempSync(join(tmpdir(), "seed-app-"));
  return {
    root,
    async cleanup() {
      for (let attempt = 0; attempt < 80; attempt += 1) {
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

async function waitFor(predicate: () => boolean, timeoutMs = 20000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error("timeout");
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
}

test("App 真实链路：JSONL 事件 -> 真实模型 HTTP -> worker 进程写文件 -> 报告 -> 回复", async () => {
  const dir = workspace();
  const mock = await mockModel([
    '{"kind":"accept","strength":"explicit","reason":"asked","scope":"ticket"}',
    '{"action":"tool","tool":"write_file","args":{"path":"result.txt","content":"由真实 worker 写入"}}',
    '{"action":"report","status":"ready","summary":"result.txt 已生成"}',
  ]);

  const inbox = join(dir.root, "inbox.jsonl");
  writeFileSync(
    inbox,
    `${JSON.stringify({
      id: "trg-e2e-1",
      source: "local",
      actor: "alice",
      text: "写一个 result.txt",
      threadIds: ["local:e2e"],
      channelIds: ["local:e2e"],
    })}\n`,
  );

  const config = parseConfig({
    dbPath: join(dir.root, "state.db"),
    workRoot: join(dir.root, "work"),
    slots: 1,
    intervalMs: 10,
    model: { baseUrl: mock.baseUrl, apiKeyEnv: "SEED_TEST_KEY", name: "test-model" },
    sources: { local: { inbox } },
  });

  const app = App.create({ config, env: { SEED_TEST_KEY: "sk-test" } });
  try {
    await app.runOnce();
    await waitFor(() => Object.values(app.runtime.engine.state.tickets)[0]?.state === "ended");
    await app.runOnce();

    const ticket = Object.values(app.runtime.engine.state.tickets)[0];
    assert.ok(ticket);
    const workDir = join(dir.root, "work", ticket.shortName);
    assert.ok(existsSync(join(workDir, "result.txt")), "worker should write into its ticket directory");
    assert.match(readFileSync(join(workDir, "result.txt"), "utf8"), /真实 worker/);
    assert.equal(app.runtime.engine.state.sentMessages.size, 1, "ready 报告应触发一条对外回复");
  } finally {
    app.stop();
    mock.close();
    await dir.cleanup();
  }
});

test("App 缺少模型密钥时给出明确错误", async () => {
  const config = parseConfig({
    dbPath: ":memory:",
    model: { baseUrl: "http://127.0.0.1:1", apiKeyEnv: "SEED_MISSING_KEY", name: "m" },
    sources: { local: { inbox: "inbox.jsonl" } },
  });
  assert.throws(() => App.create({ config, env: {} }), AppError);
});

test("App 未配置任何 Source 时拒绝启动", () => {
  const config = parseConfig({
    model: { baseUrl: "http://127.0.0.1:1", apiKeyEnv: "SEED_ANY", name: "m" },
  });
  assert.throws(() => App.create({ config, env: { SEED_ANY: "k" } }), /sources is empty/);
});