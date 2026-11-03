/** 控制台信道：本地/验证场景把对外消息打到 stdout，便于人直接看。 */
export class ConsoleChannel {
    prefix;
    constructor(prefix = "[seed]") {
        this.prefix = prefix;
    }
    async send(channel, text) {
        process.stdout.write(`${this.prefix} -> ${channel.address}: ${text}\n`);
    }
}
//# sourceMappingURL=console.js.map