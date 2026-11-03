/** 策略与确定性准入（Gate = Fast Path）。模型侧策略在提示词里（Slow Path）。 */
import type { AcceptMode, Policy, PolicyRule, Strength, Trigger } from "./domain.ts";
export interface GateResult {
    readonly allowed: boolean;
    readonly strength: Strength;
    readonly rule?: PolicyRule;
    readonly reason: string;
}
export declare function buildPolicy(rules?: readonly PolicyRule[], acceptMode?: AcceptMode, allowedSenders?: readonly (readonly [string, string])[], options?: {
    mentionRequiredFor?: readonly string[];
    mentionTokens?: readonly string[];
}): Policy;
export declare function senderAllowed(policy: Policy, source: string, actor: string): boolean;
export declare function gate(policy: Policy | null, trigger: Trigger): GateResult;
/** 开箱策略：只接受显式请求，其它一律过滤。 */
export declare function defaultPolicy(): Policy;
