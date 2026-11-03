/** 飞书命令行小工具：验证真实收发（say 发送 / read 拉取）。 */
import { mergeEnv } from "./env.js";
import { FeishuHttpClient } from "./sources/feishu_http.js";
function client(chatIds) {
    const env = mergeEnv(undefined, process.env.SEED_ENV_FILE);
    const appId = env.FEISHU_APP_ID;
    const appSecret = env.FEISHU_APP_SECRET;
    if (!appId || !appSecret) {
        throw new Error("missing FEISHU_APP_ID / FEISHU_APP_SECRET (seed.env)");
    }
    return new FeishuHttpClient({ appId, appSecret, chatIds });
}
export async function say(chatId, text) {
    if (!chatId || !text)
        throw new Error("usage: say <chat_id> <text>");
    const result = await client([chatId]).reply(chatId, undefined, text);
    console.log(`sent to ${chatId}: message_id=${result.id}`);
    return 0;
}
export async function read(chatId) {
    if (!chatId)
        throw new Error("usage: read <chat_id>");
    const messages = await client([chatId]).listMessages();
    console.log(JSON.stringify(messages.slice(0, 20), null, 2));
    return 0;
}
//# sourceMappingURL=feishu_cli.js.map