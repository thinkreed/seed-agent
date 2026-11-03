/**
 * 邮件草稿信道（文章 §4.2）：个人助手场景下先起草结构化邮件，再由人确认发送。
 * 不直接连 SMTP：产物是标准 .eml 草稿，避免凭据进入模型上下文。
 */
import type { Clock } from "../clock.ts";
import type { Channel } from "../domain.ts";
import type { ChannelWriter } from "../ports.ts";
export declare class EmailDraftChannel implements ChannelWriter {
    private readonly dir;
    private readonly clock;
    private counter;
    constructor(dir: string, clock?: Clock);
    send(channel: Channel, text: string): Promise<void>;
}
