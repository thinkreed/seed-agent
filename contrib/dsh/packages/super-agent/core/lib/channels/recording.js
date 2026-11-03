/** 记录消息的信道替身：测试与演示用，不真正联网。 */
export class RecordingChannel {
    sent = [];
    failTimes = 0;
    async send(channel, text) {
        if (this.failTimes > 0) {
            this.failTimes -= 1;
            throw new Error("channel down");
        }
        this.sent.push({ channel, text });
    }
}
//# sourceMappingURL=recording.js.map