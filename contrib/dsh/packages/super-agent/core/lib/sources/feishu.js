/** 飞书/IM 渠道：把消息流转成 Trigger，把回复写回话题。 */
export function feishuThreadAddress(chatId, threadId) {
    return threadId ? `fs:${chatId}:${threadId}` : `fs:${chatId}`;
}
export function parseFeishuAddress(address) {
    const match = /^fs:([^:]+)(?::(.+))?$/.exec(address);
    if (!match)
        throw new Error(`bad feishu address: ${address}`);
    const [, chatId, threadId] = match;
    return threadId ? { chatId: chatId, threadId } : { chatId: chatId };
}
export class FeishuSource {
    name = "feishu";
    client;
    sinceSeconds;
    now;
    constructor(client, options = {}) {
        this.client = client;
        this.sinceSeconds = options.sinceSeconds ?? 600;
        this.now = options.now ?? (() => Date.now() / 1000);
    }
    async poll() {
        const threshold = this.now() - this.sinceSeconds;
        const messages = await this.client.listMessages();
        return messages
            .filter((message) => message.at >= threshold && isHumanText(message))
            .map((message) => ({
            id: `fs:${message.chatId}:${message.id}`,
            source: "feishu",
            actor: message.sender,
            text: message.text,
            threadIds: [feishuThreadAddress(message.chatId, message.threadId)],
            channelIds: [feishuThreadAddress(message.chatId, message.threadId)],
            at: message.at,
        }))
            .sort((a, b) => a.at - b.at || a.id.localeCompare(b.id));
    }
}
/** 过滤系统/模板消息：发送者为空或内容是群事件模板的，都不算人的指令。 */
function isHumanText(message) {
    if (!message.sender || !message.text.trim())
        return false;
    return !message.text.includes('"template"');
}
export class FeishuChannel {
    client;
    constructor(client) {
        this.client = client;
    }
    async send(channel, text) {
        const { chatId, threadId } = parseFeishuAddress(channel.address);
        await this.client.reply(chatId, threadId, text);
    }
}
//# sourceMappingURL=feishu.js.map