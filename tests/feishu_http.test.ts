import assert from "node:assert/strict";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { test } from "node:test";

import { FeishuHttpClient } from "../src/sources/feishu_http.ts";

interface MockFeishu {
  readonly baseUrl: string;
  readonly calls: { method: string; url: string; body: string }[];
  close(): void;
}

function mockFeishu(): Promise<MockFeishu> {
  const calls: { method: string; url: string; body: string }[] = [];
  const server: Server = createServer((request, response) => {
    let body = "";
    request.on("data", (chunk) => (body += String(chunk)));
    request.on("end", () => {
      calls.push({ method: request.method ?? "", url: request.url ?? "", body });
      const send = (payload: unknown): void => {
        response.writeHead(200, { "content-type": "application/json" });
        response.end(JSON.stringify(payload));
      };
      if (request.url?.includes("/open-apis/bot/v3/info")) {
        send({ code: 0, bot: { open_id: "ou_bot" } });
        return;
      }
      if (request.url?.includes("tenant_access_token")) {
        send({ code: 0, tenant_access_token: "t-123", expire: 7200 });
        return;
      }
      if (request.url?.startsWith("/open-apis/im/v1/messages?") && request.method === "GET") {
        send({
          code: 0,
          data: {
            items: [
              {
                message_id: "om_1",
                chat_id: "oc_1",
                root_id: "om_root",
                create_time: "1700000000000",
                sender: { id: "ou_alice" },
                body: { content: JSON.stringify({ text: "帮我修个 bug" }) },
              },
              {
                message_id: "om_bot",
                chat_id: "oc_1",
                create_time: "1700000000500",
                sender: { id: "ou_bot" },
                body: { content: JSON.stringify({ text: "机器人自己的消息" }) },
              },
              {
                message_id: "om_2",
                chat_id: "oc_1",
                create_time: "1700000001000",
                sender: { id: "ou_bob" },
                body: { content: JSON.stringify({ text: "顺便看下 CI" }) },
              },
            ],
          },
        });
        return;
      }
      send({ code: 0, data: { message_id: "om_reply" } });
    });
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const port = (server.address() as AddressInfo).port;
      resolve({ baseUrl: `http://127.0.0.1:${port}`, calls, close: () => server.close() });
    });
  });
}

test("FeishuHttpClient：拉取群消息（token 只取一次）并映射 thread", async () => {
  const mock = await mockFeishu();
  try {
    const client = new FeishuHttpClient({
      appId: "cli_a",
      appSecret: "sec",
      chatIds: ["oc_1"],
      baseUrl: mock.baseUrl,
    });
    const messages = await client.listMessages();

    assert.equal(messages.length, 2);
    assert.ok(messages.every((message) => message.sender !== "ou_bot"), "机器人的消息应被过滤");
    assert.equal(messages[0]?.sender, "ou_alice");
    assert.equal(messages[0]?.text, "帮我修个 bug");
    assert.equal(messages[0]?.threadId, "om_root");
    assert.equal(messages[0]?.at, 1_700_000_000);
    assert.equal(messages[1]?.threadId, undefined);

    await client.listMessages();
    const tokenCalls = mock.calls.filter((call) => call.url.includes("tenant_access_token"));
    assert.equal(tokenCalls.length, 1);
    const tokenCall = tokenCalls[0];
    assert.match(tokenCall?.body ?? "", /"app_id":"cli_a"/);
  } finally {
    mock.close();
  }
});

test("FeishuHttpClient：有 thread 用 reply，无 thread 用 send", async () => {
  const mock = await mockFeishu();
  try {
    const client = new FeishuHttpClient({
      appId: "a",
      appSecret: "s",
      chatIds: ["oc_1"],
      baseUrl: mock.baseUrl,
    });
    await client.reply("oc_1", "om_root", "收到，已排期");
    await client.reply("oc_1", undefined, "普通回复");

    const replyCall = mock.calls.find((call) => call.url.includes("/reply"));
    assert.ok(replyCall);
    assert.match(replyCall?.url ?? "", /om_root\/reply/);
    assert.match(replyCall?.body ?? "", /收到，已排期/);

    const sendCall = mock.calls.find((call) => call.url.includes("receive_id_type=chat_id"));
    assert.ok(sendCall);
    assert.match(sendCall?.body ?? "", /"receive_id":"oc_1"/);
  } finally {
    mock.close();
  }
});

test("FeishuHttpClient：HTTP 错误会抛错（由 outbox 退避）", async () => {
  const server = createServer((_request, response) => {
    response.writeHead(500);
    response.end("boom");
  });
  const port = await new Promise<number>((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve((server.address() as AddressInfo).port));
  });
  try {
    const client = new FeishuHttpClient({
      appId: "a",
      appSecret: "s",
      chatIds: ["oc_1"],
      baseUrl: `http://127.0.0.1:${port}`,
    });
    await assert.rejects(client.listMessages(), /feishu HTTP 500/);
  } finally {
    server.close();
  }
});