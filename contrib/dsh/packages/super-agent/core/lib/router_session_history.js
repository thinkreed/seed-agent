/** Router 对话历史的轻量落盘：跨进程重启保留最近对话，不是业务状态。 */
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
const MAX_MESSAGES = 200;
export function loadChatHistory(path) {
    if (!path || !existsSync(path))
        return [];
    try {
        const payload = JSON.parse(readFileSync(path, "utf8"));
        if (!Array.isArray(payload.messages))
            return [];
        return payload.messages
            .filter((item) => typeof item === "object" &&
            item !== null &&
            (item.role === "user" || item.role === "assistant") &&
            typeof item.content === "string")
            .slice(-MAX_MESSAGES);
    }
    catch {
        return [];
    }
}
export function saveChatHistory(path, messages) {
    if (!path)
        return;
    try {
        mkdirSync(dirname(path), { recursive: true });
        const temp = `${path}.tmp`;
        writeFileSync(temp, JSON.stringify({ version: 1, messages: messages.slice(-MAX_MESSAGES) }), "utf8");
        renameSync(temp, path);
    }
    catch {
        // 对话历史落盘失败不应影响回复；下次启动丢掉这段历史即可。
    }
}
//# sourceMappingURL=router_session_history.js.map