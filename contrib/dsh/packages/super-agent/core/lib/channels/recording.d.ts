/** 记录消息的信道替身：测试与演示用，不真正联网。 */
import type { Channel } from "../domain.ts";
import type { ChannelWriter } from "../ports.ts";
export declare class RecordingChannel implements ChannelWriter {
    readonly sent: {
        channel: Channel;
        text: string;
    }[];
    failTimes: number;
    send(channel: Channel, text: string): Promise<void>;
}
