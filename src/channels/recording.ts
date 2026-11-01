/** 记录消息的信道替身：测试与演示用，不真正联网。 */

import type { Channel } from "../domain.ts";
import type { ChannelWriter } from "../ports.ts";

export class RecordingChannel implements ChannelWriter {
  readonly sent: { channel: Channel; text: string }[] = [];
  failTimes = 0;

  async send(channel: Channel, text: string): Promise<void> {
    if (this.failTimes > 0) {
      this.failTimes -= 1;
      throw new Error("channel down");
    }
    this.sent.push({ channel, text });
  }
}