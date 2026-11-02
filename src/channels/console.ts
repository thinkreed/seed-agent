/** 控制台信道：本地/验证场景把对外消息打到 stdout，便于人直接看。 */

import type { Channel } from "../domain.ts";
import type { ChannelWriter } from "../ports.ts";

export class ConsoleChannel implements ChannelWriter {
  private readonly prefix: string;

  constructor(prefix = "[seed]") {
    this.prefix = prefix;
  }

  async send(channel: Channel, text: string): Promise<void> {
    process.stdout.write(`${this.prefix} -> ${channel.address}: ${text}\n`);
  }
}