import assert from "node:assert/strict";
import { createServer } from "node:http";
import { test } from "node:test";

import { OpenAIClient } from "../src/llm/openai.ts";

async function withServer(
  handler: Parameters<typeof createServer>[1],
  run: (baseUrl: string) => Promise<void>,
): Promise<void> {
  const server = createServer(handler);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : 0;
  try {
    await run(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
}

test("模型 5xx/429 按 Retry-After 重试，随后成功", async () => {
  let calls = 0;
  await withServer(
    (_request, response) => {
      calls += 1;
      if (calls === 1) {
        response.writeHead(503, { "retry-after": "0" });
        response.end("busy");
        return;
      }
      if (calls === 2) {
        response.writeHead(429, { "retry-after": "0" });
        response.end("rate limited");
        return;
      }
      response.end(JSON.stringify({ choices: [{ message: { content: "ok" } }] }));
    },
    async (baseUrl) => {
      const client = new OpenAIClient({
        baseUrl,
        apiKey: "test-key",
        model: "m",
        maxRetries: 2,
        timeoutMs: 1000,
      });
      assert.equal(await client.complete([{ role: "user", content: "hi" }]), "ok");
      assert.equal(calls, 3);
    },
  );
});

test("模型错误信息会脱敏 sk-/Bearer", async () => {
  await withServer(
    (_request, response) => {
      response.writeHead(500);
      response.end("bad key sk-abc123456 and Bearer abcdef123456");
    },
    async (baseUrl) => {
      const client = new OpenAIClient({ baseUrl, apiKey: "k", model: "m", maxRetries: 0 });
      await assert.rejects(client.complete([{ role: "user", content: "hi" }]), (error: Error) => {
        assert.ok(!error.message.includes("sk-abc123456"));
        assert.ok(!error.message.includes("abcdef123456"));
        assert.match(error.message, /sk-\*\*\*/);
        return true;
      });
    },
  );
});

test("模型超时会失败而不是永久挂起", async () => {
  await withServer(
    () => {
      // 永不响应
    },
    async (baseUrl) => {
      const client = new OpenAIClient({
        baseUrl,
        apiKey: "k",
        model: "m",
        maxRetries: 0,
        timeoutMs: 30,
      });
      await assert.rejects(client.complete([{ role: "user", content: "hi" }]), /model request failed/);
    },
  );
});