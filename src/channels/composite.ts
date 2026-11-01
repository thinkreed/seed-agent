/** 组合信道：按地址前缀把消息路由到对应渠道（gh: / fs: / 其它）。 */

import type { Channel } from "../domain.ts";
import type { ChannelWriter } from "../ports.ts";

export interface ChannelRoute {
  readonly prefix: string;
  readonly writer: ChannelWriter;
}

export class CompositeChannel implements ChannelWriter {
  private readonly routes: readonly ChannelRoute[];

  constructor(routes: readonly ChannelRoute[]) {
    this.routes = routes;
  }

  async send(channel: Channel, text: string): Promise<void> {
    const route = this.routes.find((item) => channel.address.startsWith(item.prefix));
    if (!route) throw new Error(`no channel route for address: ${channel.address}`);
    await route.writer.send(channel, text);
  }
}