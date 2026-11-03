/**
 * 文档信道（文章 §4.2）：把结构化交付写成 Markdown，供人直接阅读或归档。
 * 同一地址的多次更新追加到同一文档，保留时间线。
 */
import type { Clock } from "../clock.ts";
import type { Channel } from "../domain.ts";
import type { ChannelWriter } from "../ports.ts";
export declare class DocsChannel implements ChannelWriter {
    private readonly dir;
    private readonly clock;
    constructor(dir: string, clock?: Clock);
    send(channel: Channel, text: string): Promise<void>;
}
