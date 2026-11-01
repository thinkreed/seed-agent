import assert from "node:assert/strict";
import { test } from "node:test";

import {
  FeishuChannel,
  FeishuSource,
  feishuThreadAddress,
  parseFeishuAddress,
  type FeishuClient,
  type FeishuMessage,
} from "../src/sources/feishu.ts";

class FakeFeishu implements FeishuClient {
  messages: FeishuMessage[] = [];
  readonly replies: { chatId: string; threadId?: string; text: string }[] = [];

  async listMessages(): Promise<FeishuMessage[]> {
    return [...this.messages];
  }

  async reply(chatId: string, threadId: string | undefined, text: string): Promise<{ id: string }> {
    this.replies.push({ chatId, threadId, text });
    return { id: `r-${this.replies.length}` };
  }
}

function message(overrides: Partial<FeishuMessage> = {}): FeishuMessage {
  return {
    id: "m-1",
    chatId: "oc_123",
    threadId: "om_9",
    sender: "alice",
    text: "帮我看看这个 500",
    at: 1_700_000_000,
    ...overrides,
  };
}

test("feishuThreadAddress / parseFeishuAddress：可逆", () => {
  assert.equal(feishuThreadAddress("oc_1", "om_2"), "fs:oc_1:om_2");
  assert.deepEqual(parseFeishuAddress("fs:oc_1:om_2"), { chatId: "oc_1", threadId: "om_2" });
  assert.deepEqual(parseFeishuAddress("fs:oc_1"), { chatId: "oc_1" });
  assert.throws(() => parseFeishuAddress("nope"), /bad feishu address/);
});

test("FeishuSource：消息 -> Trigger，同一话题归同一 Thread", async () => {
  const client = new FakeFeishu();
  client.messages = [
    message({ id: "m-2", at: 1_700_000_200 }),
    message({ id: "m-1", at: 1_700_000_100 }),
    message({ id: "m-3", threadId: undefined, at: 1_700_000_300 }),
  ];
  const source = new FeishuSource(client);
  const triggers = await source.poll();

  assert.equal(triggers.length, 3);
  assert.deepEqual(
    triggers.map((item) => item.at),
    [1_700_000_100, 1_700_000_200, 1_700_000_300],
  );
  assert.equal(triggers[0]?.threadIds[0], "fs:oc_123:om_9");
  assert.equal(triggers[2]?.threadIds[0], "fs:oc_123");
  assert.equal(triggers[0]?.source, "feishu");
});

test("FeishuSource：重复轮询产生相同 id（引擎侧幂等）", async () => {
  const client = new FakeFeishu();
  client.messages = [message()];
  const source = new FeishuSource(client);
  const first = await source.poll();
  const second = await source.poll();
  assert.deepEqual(first.map((item) => item.id), second.map((item) => item.id));
});

test("FeishuChannel：回复发到对应话题", async () => {
  const client = new FakeFeishu();
  const channel = new FeishuChannel(client);
  await channel.send({ address: "fs:oc_123:om_9" }, "已完成，请验收");
  assert.deepEqual(client.replies, [{ chatId: "oc_123", threadId: "om_9", text: "已完成，请验收" }]);
});

test("FeishuChannel：地址非法时抛错（由 outbox 退避）", async () => {
  const channel = new FeishuChannel(new FakeFeishu());
  await assert.rejects(channel.send({ address: "bad" }, "x"));
});