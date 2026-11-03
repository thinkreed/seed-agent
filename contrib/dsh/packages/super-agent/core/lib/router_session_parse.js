/** Router Session 的纯解析辅助：模型输出 → Decision/Recall（无 IO，可单测）。 */
export function ignored(reason) {
    return { kind: "ignore", strength: "inferred", reason, scope: "ticket", rules: [] };
}
export function parsePayload(raw) {
    const start = raw.indexOf("{");
    const end = raw.lastIndexOf("}");
    if (start < 0 || end <= start)
        return undefined;
    try {
        const parsed = JSON.parse(raw.slice(start, end + 1));
        return parsed && typeof parsed === "object" && !Array.isArray(parsed)
            ? parsed
            : undefined;
    }
    catch {
        return undefined;
    }
}
export function readRecalls(payload) {
    const raw = payload.recall;
    if (!Array.isArray(raw))
        return [];
    const kinds = ["trigger", "thread", "ticket"];
    return raw.flatMap((item) => {
        if (!item || typeof item !== "object")
            return [];
        const record = item;
        const kind = typeof record.kind === "string" && kinds.includes(record.kind)
            ? record.kind
            : undefined;
        const id = typeof record.id === "string" ? record.id : undefined;
        return kind && id ? [{ kind, id }] : [];
    });
}
export function readDecisions(payload) {
    const raw = payload.decisions;
    const map = new Map();
    if (!Array.isArray(raw))
        return map;
    for (const item of raw) {
        if (!item || typeof item !== "object")
            continue;
        const record = item;
        const threadId = typeof record.threadId === "string" ? record.threadId : undefined;
        if (!threadId)
            continue;
        map.set(threadId, decisionOf(record));
    }
    return map;
}
export function decisionOf(record) {
    const kind = record.kind;
    if (kind !== "accept" &&
        kind !== "stop" &&
        kind !== "ignore" &&
        kind !== "unavailable" &&
        kind !== "reply") {
        return ignored("bad-kind");
    }
    const strength = record.strength === "explicit" ? "explicit" : "inferred";
    const reason = typeof record.reason === "string" ? record.reason.slice(0, 300) : "";
    const scope = typeof record.scope === "string" && record.scope ? record.scope : "ticket";
    const rules = Array.isArray(record.rules)
        ? record.rules.filter((entry) => typeof entry === "string").slice(0, 10)
        : [];
    const reply = typeof record.reply === "string" ? record.reply.slice(0, 2000) : undefined;
    const title = typeof record.title === "string" && record.title.trim() ? record.title.trim().slice(0, 80) : undefined;
    return { kind, strength, reason, scope, rules, ...(reply ? { reply } : {}), ...(title ? { title } : {}) };
}
export function parseChatResult(raw) {
    const payload = parsePayload(raw);
    const reply = payload && typeof payload.reply === "string" && payload.reply.trim() ? payload.reply.trim() : raw.trim();
    const work = payload && typeof payload.work === "string" && payload.work.trim() ? payload.work.trim() : undefined;
    return { reply, ...(work ? { work } : {}) };
}
export function parseChatReply(raw) {
    return parseChatResult(raw).reply;
}
//# sourceMappingURL=router_session_parse.js.map