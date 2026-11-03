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
export declare class FeishuHttpClient implements FeishuClient {
    private readonly options;
    private token;
    private botOpenId;
    constructor(options: FeishuHttpOptions);
    listMessages(): Promise<FeishuMessage[]>;
    private resolveBotOpenId;
    reply(chatId: string, threadId: string | undefined, text: string): Promise<{
        id: string;
    }>;
    private toMessage;
    private tenantToken;
    private request;
    private raw;
}
