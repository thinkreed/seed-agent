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
    reply(chatId: string, threadId: string | undefined, text: string): Promise<{
        id: string;
    }>;
}
export declare function feishuThreadAddress(chatId: string, threadId?: string): string;
export declare function parseFeishuAddress(address: string): {
    chatId: string;
    threadId?: string;
};
export interface FeishuSourceOptions {
    /** 只处理最近 N 秒的消息，避免首次启动把历史消息全部当成新任务。 */
    readonly sinceSeconds?: number;
    readonly now?: () => number;
}
export declare class FeishuSource implements Source {
    readonly name = "feishu";
    private readonly client;
    private readonly sinceSeconds;
    private readonly now;
    constructor(client: FeishuClient, options?: FeishuSourceOptions);
    poll(): Promise<Trigger[]>;
}
export declare class FeishuChannel implements ChannelWriter {
    private readonly client;
    constructor(client: FeishuClient);
    send(channel: {
        address: string;
    }, text: string): Promise<void>;
}
