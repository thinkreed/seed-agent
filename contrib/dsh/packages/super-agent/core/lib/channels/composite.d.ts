/** 组合信道：按地址前缀把消息路由到对应渠道（gh: / fs: / 其它）。 */
import type { Channel } from "../domain.ts";
import type { ChannelWriter } from "../ports.ts";
export interface ChannelRoute {
    readonly prefix: string;
    readonly writer: ChannelWriter;
}
export declare class CompositeChannel implements ChannelWriter {
    private readonly routes;
    constructor(routes: readonly ChannelRoute[]);
    send(channel: Channel, text: string): Promise<void>;
}
