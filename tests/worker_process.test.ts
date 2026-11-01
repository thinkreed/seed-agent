import assert from "node:assert/strict";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { test } from "node:test";

const REPO = join(import.meta.dirname, "..");

interface MockModel {
  readonly baseUrl: string;
  readonly contents: string[];
  close(): void;
}

/** 真实 HTTP server 扮演模型端点：按脚本依次回 reply。 */
function mockModel(replies: string[]): Promise<MockModel> {
  const contents: string[] = [...replies];
  const server: Server = createServer((request, response) => {
    request.on("data", () => undefined);
    request.on("end", () => {
      const content = contents.shift() ?? '{"action":"report","status":"failed","summary":"no reply"}';
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ choices: [{ message: { content } }] }));
    });
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const port = (server.address() as AddressInfo).port;
      resolve({
        baseUrl: `http://127.0.0.1:${port}`,
        contents,
        close: () => server.close(),
      });
    });
  });
}

function workspace(): { root: string; cleanup: () => Promise<void> } {
  const root = mkdtempSync(join(tmpdir(), "seed-worker-"));
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

test("worker 进程：真实模型调用 + 真实文件工具 + 结构化报告", async () => {
  const dir = workspace();
  const mock = await mockModel([
    '{"action":"tool","tool":"write_file","args":{"path":"result.txt","content":"done by worker"}}',
    '{"action":"report","status":"ready","summary":"写好了 result.txt"}',
  ]);

  const child = spawn(process.execPath, [join(REPO, "src", "worker", "main.ts")], {
    cwd: REPO,
    env: {
      ...process.env,
      SEED_WORKER_ROOT: dir.root,
      SEED_WORKER_TICKET: "tk-1",
      SEED_WORKER_SHORT_NAME: "t-1",
      SEED_WORKER_SCOPE: "ticket",
      SEED_WORKER_INPUT: JSON.stringify([
        { id: "trg-1", source: "local", actor: "alice", text: "写个文件", threadIds: [], channelIds: [], at: 0 },
      ]),
      SEED_MODEL_BASE_URL: mock.baseUrl,
      SEED_MODEL_API_KEY: "sk-test",
      SEED_MODEL_NAME: "deepseek-chat",
    },
    stdio: ["pipe", "pipe", "pipe"],
  });

  const reports: string[] = [];
  createInterface({ input: child.stdout! }).on("line", (line) => reports.push(line));

  const deadline = Date.now() + 15000;
  while (reports.length === 0) {
    if (Date.now() > deadline) throw new Error(`timeout; stderr=${String(child.stderr?.read?.() ?? "")}`);
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  child.kill();

  const report = JSON.parse(reports[0] ?? "{}") as { type: string; status: string; summary: string };
  assert.equal(report.type, "report");
  assert.equal(report.status, "ready");
  assert.match(report.summary, /result\.txt/);
  assert.equal(readFileSync(join(dir.root, "result.txt"), "utf8"), "done by worker");

  mock.close();
  await dir.cleanup();
  child.unref();
});