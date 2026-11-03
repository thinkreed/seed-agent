/**
 * 飞书客户端（真实 HTTP）：tenant_access_token + 拉取群消息 + 话题回复。
 * 需要 app_id / app_secret（企业自建应用，开通 im:message 权限）。
 */
export class FeishuHttpClient {
    options;
    token;
    botOpenId;
    constructor(options) {
        this.options = options;
    }
    async listMessages() {
        const botOpenId = await this.resolveBotOpenId();
        const collected = [];
        for (const chatId of this.options.chatIds) {
            const response = await this.request("GET", `/open-apis/im/v1/messages?container_id_type=chat&container_id=${encodeURIComponent(chatId)}&sort_type=ByCreateTimeDesc&page_size=50`);
            for (const item of response.data?.items ?? []) {
                const message = this.toMessage(item, chatId);
                const self = message !== null && (message.sender === botOpenId || message.sender === this.options.appId);
                if (message && !self)
                    collected.push(message);
            }
        }
        return collected;
    }
    async resolveBotOpenId() {
        if (this.botOpenId !== undefined)
            return this.botOpenId;
        try {
            const info = await this.request("GET", "/open-apis/bot/v3/info");
            this.botOpenId = info.bot?.open_id ?? null;
        }
        catch {
            this.botOpenId = null;
        }
        return this.botOpenId;
    }
    async reply(chatId, threadId, text) {
        const content = JSON.stringify({ text });
        if (threadId) {
            const result = await this.request("POST", `/open-apis/im/v1/messages/${encodeURIComponent(threadId)}/reply`, { msg_type: "text", content });
            return { id: result.data?.message_id ?? threadId };
        }
        const result = await this.request("POST", "/open-apis/im/v1/messages?receive_id_type=chat_id", { receive_id: chatId, msg_type: "text", content });
        return { id: result.data?.message_id ?? "" };
    }
    toMessage(item, fallbackChatId) {
        if (!item.message_id)
            return null;
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
    async tenantToken() {
        if (this.token && this.token.expiresAt > Date.now())
            return this.token.value;
        const response = await this.raw("/open-apis/auth/v3/tenant_access_token/internal", {
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
    async request(method, path, body) {
        const token = await this.tenantToken();
        return this.raw(path, method === "POST" ? body : undefined, { method, token });
    }
    async raw(path, body, options = {}) {
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
            if (!response.ok)
                throw new Error(`feishu HTTP ${response.status}`);
            return (await response.json());
        }
        finally {
            clearTimeout(timer);
        }
    }
}
function parseText(content) {
    if (!content)
        return "";
    try {
        const parsed = JSON.parse(content);
        if (parsed && typeof parsed === "object" && "text" in parsed) {
            return String(parsed.text ?? "");
        }
    }
    catch {
        return content;
    }
    return content;
}
//# sourceMappingURL=feishu_http.js.map