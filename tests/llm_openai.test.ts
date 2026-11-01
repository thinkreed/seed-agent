import assert from "node:assert/strict";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { test } from "node:test";

import { OpenAIClient } from "../src/llm/openai.ts";

interface Mock {
  readonly baseUrl: string;
  readonly requests: { authorization?: string; body: string }[];
  close(): void;
}

function startServer(handler: (body: string) => { status: number; json: unknown }): Promise<Mock> {
  const requests: { authorization?: string; body: string }[] = [];
  const server: Server = createServer((request, response) => {
    let body = "";
    request.on("data", (chunk) => (body += String(chunk)));
    request.on("end", () => {
      requests.push({ authorization: request.headers.authorization, body });
      const result = handler(body);
      response.writeHead(result.status, { "content-type": "application/json" });
      response.end(JSON.stringify(result.json));
    });
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const port = (server.address() as AddressInfo).port;
      resolve({ baseUrl: `http://127.0.0.1:${port}`, requests, close: () => server.close() });
    });
  });
}

function chat(content: string): { status: number; json: unknown } {
  return { status: 200, json: { choices: [{ message: { content } }] } };
}

test("OpenAIClient：真实 HTTP 调用并取回 content", async () => {
  const mock = await startServer(() => chat("hello from model"));
  try {
    const client = new OpenAIClient({ baseUrl: mock.baseUrl, apiKey: "sk-test", model: "deepseek-chat" });
    const content = await client.complete([{ role: "user", content: "hi" }]);
    assert.equal(content, "hello from model");
    assert.equal(mock.requests[0]?.authorization, "Bearer sk-test");
    assert.match(mock.requests[0]?.body ?? "", /"model":"deepseek-chat"/);
  } finally {
    mock.close();
  }
});

test("OpenAIClient：5xx 会重试并最终成功", async () => {
  let calls = 0;
  const mock = await startServer(() => {
    calls += 1;
    return calls === 1 ? { status: 500, json: { error: "boom" } } : chat("after retry");
  });
  try {
    const client = new OpenAIClient({ baseUrl: mock.baseUrl, apiKey: "k", model: "m", maxRetries: 1 });
    assert.equal(await client.complete([{ role: "user", content: "hi" }]), "after retry");
    assert.equal(mock.requests.length, 2);
  } finally {
    mock.close();
  }
});

test("OpenAIClient：401 不重试，直接抛错", async () => {
  const mock = await startServer(() => ({ status: 401, json: { error: { message: "denied" } } }));
  try {
    const client = new OpenAIClient({ baseUrl: mock.baseUrl, apiKey: "bad", model: "m", maxRetries: 3 });
    await assert.rejects(client.complete([{ role: "user", content: "hi" }]), /model request failed/);
    assert.equal(mock.requests.length, 1);
  } finally {
    mock.close();
  }
});

test("OpenAIClient：响应缺 content 时抛错", async () => {
  const mock = await startServer(() => ({ status: 200, json: { choices: [{ message: {} }] } }));
  try {
    const client = new OpenAIClient({ baseUrl: mock.baseUrl, apiKey: "k", model: "m", maxRetries: 0 });
    await assert.rejects(client.complete([{ role: "user", content: "hi" }]), /model request failed/);
  } finally {
    mock.close();
  }
});

test("OpenAIClient：连接失败时按重试次数报错", async () => {
  const client = new OpenAIClient({
    baseUrl: "http://127.0.0.1:9",
    apiKey: "k",
    model: "m",
    maxRetries: 1,
    timeoutMs: 2000,
  });
  await assert.rejects(client.complete([{ role: "user", content: "hi" }]), /model request failed/);
});