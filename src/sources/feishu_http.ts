/**
 * 飞书客户端（真实 HTTP）：tenant_access_token + 拉取群消息 + 话题回复。
 * 需要 app_id / app_secret（企业自建应用，开通 im:message 权限）。
 */

import type { FeishuClient, FeishuMessage } from "./feishu.ts";

export interface FeishuHttpOptions {
  readonly appId: string;
  readonly appSecret: string;
  /** 需要轮询的群 chat_id 列表。 */
  readonly chatIds: readonly string[];
  readonly baseUrl?: string;
  readonly timeoutMs?: number;
}

interface TokenResponse {
  readonly code?: number;
  readonly msg?: string;
  readonly tenant_access_token?: string;
  readonly expire?: number;
}

interface MessageItem {
  readonly message_id?: string;
  readonly chat_id?: string;
  readonly root_id?: string;
  readonly parent_id?: string;
  readonly create_time?: string;
  readonly body?: { readonly content?: string };
  readonly sender?: { readonly id?: string };
}

interface ListResponse {
  readonly code?: number;
  readonly msg?: string;
  readonly data?: { readonly items?: MessageItem[] };
}

export class FeishuHttpClient implements FeishuClient {
  private readonly options: FeishuHttpOptions;
  private token: { value: string; expiresAt: number } | undefined;
  private botOpenId: string | null | undefined;

  constructor(options: FeishuHttpOptions) {
    this.options = options;
  }

  async listMessages(): Promise<FeishuMessage[]> {
    const botOpenId = await this.resolveBotOpenId();
    const collected: FeishuMessage[] = [];
    for (const chatId of this.options.chatIds) {
      const response = await this.request<ListResponse>(
        "GET",
        `/open-apis/im/v1/messages?container_id_type=chat&container_id=${encodeURIComponent(chatId)}&sort_type=ByCreateTimeDesc&page_size=50`,
      );
      for (const item of response.data?.items ?? []) {
        const message = this.toMessage(item, chatId);
        const self = message !== null && (message.sender === botOpenId || message.sender === this.options.appId);
        if (message && !self) collected.push(message);
      }
    }
    return collected;
  }

  private async resolveBotOpenId(): Promise<string | null> {
    if (this.botOpenId !== undefined) return this.botOpenId;
    try {
      const info = await this.request<{ bot?: { open_id?: string } }>("GET", "/open-apis/bot/v3/info");
      this.botOpenId = info.bot?.open_id ?? null;
    } catch {
      this.botOpenId = null;
    }
    return this.botOpenId;
  }

  async reply(chatId: string, threadId: string | undefined, text: string): Promise<{ id: string }> {
    const content = JSON.stringify({ text });
    if (threadId) {
      const result = await this.request<{ code?: number; data?: { message_id?: string } }>(
        "POST",
        `/open-apis/im/v1/messages/${encodeURIComponent(threadId)}/reply`,
        { msg_type: "text", content },
      );
      return { id: result.data?.message_id ?? threadId };
    }
    const result = await this.request<{ code?: number; data?: { message_id?: string } }>(
      "POST",
      "/open-apis/im/v1/messages?receive_id_type=chat_id",
      { receive_id: chatId, msg_type: "text", content },
    );
    return { id: result.data?.message_id ?? "" };
  }

  private toMessage(item: MessageItem, fallbackChatId: string): FeishuMessage | null {
    if (!item.message_id) return null;
    const threadId = item.root_id || item.parent_id || undefined;
    return {
      id: item.message_id,
      chatId: item.chat_id ?? fallbackChatId,
      ...(threadId ? { threadId } : {}),
      sender: item.sender?.id ?? "unknown",
      text: parseText(item.body?.content),
      at: Number(item.create_time ?? 0) / 1000,
    };
  }

  private async tenantToken(): Promise<string> {
    if (this.token && this.token.expiresAt > Date.now()) return this.token.value;
    const response = await this.raw<TokenResponse>("/open-apis/auth/v3/tenant_access_token/internal", {
      app_id: this.options.appId,
      app_secret: this.options.appSecret,
    });
    if (!response.tenant_access_token) {
      throw new Error(`feishu token failed: code=${String(response.code)} msg=${response.msg ?? ""}`);
    }
    const ttlSeconds = Math.max(60, (response.expire ?? 7200) - 60);
    this.token = { value: response.tenant_access_token, expiresAt: Date.now() + ttlSeconds * 1000 };
    return this.token.value;
  }

  private async request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
    const token = await this.tenantToken();
    return this.raw<T>(path, method === "POST" ? body : undefined, { method, token });
  }

  private async raw<T>(
    path: string,
    body?: unknown,
    options: { method?: "GET" | "POST"; token?: string } = {},
  ): Promise<T> {
    const base = (this.options.baseUrl ?? "https://open.feishu.cn").replace(/\/$/, "");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.options.timeoutMs ?? 30_000);
    try {
      const response = await fetch(`${base}${path}`, {
        method: options.method ?? "POST",
        headers: {
          "content-type": "application/json; charset=utf-8",
          ...(options.token ? { authorization: `Bearer ${options.token}` } : {}),
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`feishu HTTP ${response.status}`);
      return (await response.json()) as T;
    } finally {
      clearTimeout(timer);
    }
  }
}

function parseText(content: string | undefined): string {
  if (!content) return "";
  try {
    const parsed: unknown = JSON.parse(content);
    if (parsed && typeof parsed === "object" && "text" in parsed) {
      return String((parsed as { text?: unknown }).text ?? "");
    }
  } catch {
    return content;
  }
  return content;
}