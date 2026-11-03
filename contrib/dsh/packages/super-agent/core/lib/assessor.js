/** 模型决策解析：把模型输出解析成 Decision，解析失败一律降级为 ignore。 */
import { extractJsonObject } from "./json.js";
const KINDS = new Set(["accept", "stop", "ignore", "unavailable"]);
const STRENGTHS = new Set(["explicit", "inferred"]);
export function parseDecision(raw) {
    const payload = extractJsonObject(raw);
    if (!payload)
        return fallback("no-json");
    const kind = typeof payload.kind === "string" ? payload.kind : "";
    if (!KINDS.has(kind))
        return fallback(`bad-kind:${kind || "missing"}`);
    const strength = typeof payload.strength === "string" && STRENGTHS.has(payload.strength)
        ? payload.strength
        : "inferred";
    const reason = typeof payload.reason === "string" ? payload.reason.slice(0, 300) : "";
    const scope = typeof payload.scope === "string" && payload.scope ? payload.scope : "ticket";
    const rules = Array.isArray(payload.rules)
        ? payload.rules.filter((item) => typeof item === "string").slice(0, 10)
        : [];
    return { kind: kind, strength, reason, scope, rules };
}
function fallback(reason) {
    return { kind: "ignore", strength: "inferred", reason: `unparsable:${reason}`, scope: "ticket", rules: [] };
}
//# sourceMappingURL=assessor.js.map