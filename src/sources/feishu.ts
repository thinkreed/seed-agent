/** 飞书/IM 渠道：把消息流转成 Trigger，把回复写回话题。 */

import type { Trigger } from "../domain.ts";
import type { ChannelWriter, Source } from "../ports.ts";

export interface FeishuMessage {
  readonly id: string;
  readonly chatId: string;
  readonly threadId?: string;
  readonly sender: string;
  readonly text: string;
  readonly at: number;
}

export interface FeishuClient {
  listMessages(): Promise<FeishuMessage[]>;
  reply(chatId: string, threadId: string | undefined, text: string): Promise<{ id: string }>;
}

export function feishuThreadAddress(chatId: string, threadId?: string): string {
  return threadId ? `fs:${chatId}:${threadId}` : `fs:${chatId}`;
}

export function parseFeishuAddress(address: string): { chatId: string; threadId?: string } {
  const match = /^fs:([^:]+)(?::(.+))?$/.exec(address);
  if (!match) throw new Error(`bad feishu address: ${address}`);
  const [, chatId, threadId] = match;
  return threadId ? { chatId: chatId as string, threadId } : { chatId: chatId as string };
}

export class FeishuSource implements Source {
  readonly name = "feishu";
  private readonly client: FeishuClient;

  constructor(client: FeishuClient) {
    this.client = client;
  }

  async poll(): Promise<Trigger[]> {
    const messages = await this.client.listMessages();
    return messages
      .map((message) => ({
        id: `fs:${message.chatId}:${message.id}`,
        source: "feishu",
        actor: message.sender,
        text: message.text,
        threadIds: [feishuThreadAddress(message.chatId, message.threadId)],
        channelIds: [feishuThreadAddress(message.chatId, message.threadId)],
        at: message.at,
      }))
      .sort((a, b) => a.at - b.at || a.id.localeCompare(b.id));
  }
}

export class FeishuChannel implements ChannelWriter {
  private readonly client: FeishuClient;

  constructor(client: FeishuClient) {
    this.client = client;
  }

  async send(channel: { address: string }, text: string): Promise<void> {
    const { chatId, threadId } = parseFeishuAddress(channel.address);
    await this.client.reply(chatId, threadId, text);
  }
}