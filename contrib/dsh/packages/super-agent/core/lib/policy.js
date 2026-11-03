/** 策略与确定性准入（Gate = Fast Path）。模型侧策略在提示词里（Slow Path）。 */
import { createHash } from "node:crypto";
function canonical(value) {
    return JSON.stringify(value, (_key, item) => {
        if (item && typeof item === "object" && !Array.isArray(item)) {
            const sorted = {};
            for (const key of Object.keys(item).sort()) {
                sorted[key] = item[key];
            }
            return sorted;
        }
        return item;
    });
}
export function buildPolicy(rules = [], acceptMode = "auto", allowedSenders = [], options = {}) {
    const sortedSenders = [...allowedSenders].sort((a, b) => (a[0] + a[1]).localeCompare(b[0] + b[1]));
    const mentionRequiredFor = [...(options.mentionRequiredFor ?? [])].sort();
    const mentionTokens = [...(options.mentionTokens ?? [])].sort();
    const version = createHash("sha256")
        .update(canonical({
        rules: rules.map((rule) => ({
            source: rule.source,
            actor: rule.actor,
            allow: rule.allow,
            strength: rule.strength,
            note: rule.note,
        })),
        acceptMode,
        allowedSenders: sortedSenders,
        ...(mentionRequiredFor.length > 0 ? { mentionRequiredFor } : {}),
        ...(mentionTokens.length > 0 ? { mentionTokens } : {}),
    }))
        .digest("hex")
        .slice(0, 12);
    return {
        version,
        rules,
        acceptMode,
        allowedSenders: sortedSenders,
        ...(mentionRequiredFor.length > 0 ? { mentionRequiredFor } : {}),
        ...(mentionTokens.length > 0 ? { mentionTokens } : {}),
    };
}
export function senderAllowed(policy, source, actor) {
    return policy.allowedSenders.some(([allowedSource, allowedActor]) => allowedSource === source && (allowedActor === actor || allowedActor === "*"));
}
export function gate(policy, trigger) {
    if (!policy)
        return { allowed: false, strength: "inferred", reason: "no-policy" };
    if (policy.acceptMode === "off")
        return { allowed: false, strength: "inferred", reason: "policy-off" };
    if (!senderAllowed(policy, trigger.source, trigger.actor)) {
        return { allowed: false, strength: "inferred", reason: "sender-not-allowed" };
    }
    if (policy.mentionRequiredFor?.includes(trigger.source)) {
        const text = trigger.text.toLowerCase();
        const tokens = (policy.mentionTokens ?? ["@seed", "@agent"]).map((token) => token.toLowerCase());
        if (!tokens.some((token) => text.includes(token))) {
            return { allowed: false, strength: "inferred", reason: "mention-required" };
        }
    }
    for (const rule of policy.rules) {
        if (rule.source !== trigger.source)
            continue;
        if (rule.actor !== "*" && rule.actor !== trigger.actor)
            continue;
        if (!rule.allow) {
            return {
                allowed: false,
                strength: rule.strength,
                rule,
                reason: `denied-by-rule:${rule.note || "rule"}`,
            };
        }
        return {
            allowed: true,
            strength: rule.strength,
            rule,
            reason: `allowed-by-rule:${rule.note || "rule"}`,
        };
    }
    return { allowed: false, strength: "inferred", reason: "no-matching-rule" };
}
/** 开箱策略：只接受显式请求，其它一律过滤。 */
export function defaultPolicy() {
    return buildPolicy([{ source: "local", actor: "*", allow: true, strength: "explicit", note: "local-explicit" }], "auto", [["local", "*"]]);
}
//# sourceMappingURL=policy.js.map