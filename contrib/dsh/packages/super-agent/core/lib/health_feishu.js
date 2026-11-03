/** 飞书相关健康检查（token + 群里是否可见）。 */
export function feishuCheckers(config, deps) {
    const feishu = config.sources?.feishu;
    if (!feishu)
        return [];
    const env = deps.env;
    const doFetch = deps.fetchImpl ?? fetch;
    const token = async () => {
        const appId = env[feishu.appIdEnv];
        const secret = env[feishu.appSecretEnv];
        if (!appId || !secret)
            return undefined;
        const response = await doFetch("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ app_id: appId, app_secret: secret }),
        });
        const payload = (await response.json());
        return payload.tenant_access_token;
    };
    return [
        {
            name: "feishu.token",
            required: true,
            run: async () => {
                const appId = env[feishu.appIdEnv];
                const secret = env[feishu.appSecretEnv];
                if (!appId || !secret)
                    return { ok: false, detail: `missing ${feishu.appIdEnv}/${feishu.appSecretEnv}` };
                try {
                    const value = await token();
                    return value
                        ? { ok: true, detail: "tenant_access_token ok" }
                        : { ok: false, detail: "token missing (check app_id/app_secret)" };
                }
                catch (error) {
                    return { ok: false, detail: `unreachable: ${String(error).slice(0, 120)}` };
                }
            },
        },
        {
            name: "feishu.chats",
            required: true,
            run: async () => {
                const value = await token().catch(() => undefined);
                if (!value)
                    return { ok: false, detail: "skipped: no token" };
                const response = await doFetch("https://open.feishu.cn/open-apis/im/v1/chats?page_size=50", {
                    headers: { authorization: `Bearer ${value}` },
                });
                const payload = (await response.json());
                const chats = payload.data?.items ?? [];
                if (chats.length > 0) {
                    const visible = chats.filter((chat) => feishu.chatIds.includes(chat.chat_id ?? ""));
                    return visible.length > 0
                        ? { ok: true, detail: `${visible.length} configured chat(s) visible` }
                        : { ok: false, detail: `configured chatIds not visible (bot in ${chats.length} chats)` };
                }
                if (payload.code === 99991672) {
                    // 没有 im:chat 权限时退化为直接探测配置的群能否读消息
                    const chatId = feishu.chatIds[0] ?? "";
                    const probe = await doFetch(`https://open.feishu.cn/open-apis/im/v1/messages?container_id_type=chat&container_id=${encodeURIComponent(chatId)}&page_size=1`, { headers: { authorization: `Bearer ${value}` } });
                    const probePayload = (await probe.json());
                    return probePayload.code === 0
                        ? { ok: true, detail: `chat ${chatId} readable (no im:chat scope, probed messages)` }
                        : { ok: false, detail: `chat probe failed: code ${String(probePayload.code)} ${probePayload.msg ?? ""}` };
                }
                return { ok: false, detail: "bot is not in any chat: add it to a group (or give a chat_id)" };
            },
        },
    ];
}
//# sourceMappingURL=health_feishu.js.map