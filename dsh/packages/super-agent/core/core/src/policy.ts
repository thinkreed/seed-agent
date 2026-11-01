/** 策略与确定性准入（Gate = Fast Path）。模型侧策略在提示词里（Slow Path）。 */

import { createHash } from "node:crypto";

import type { AcceptMode, Policy, PolicyRule, Strength, Trigger } from "./domain.ts";

export interface GateResult {
  readonly allowed: boolean;
  readonly strength: Strength;
  readonly rule?: PolicyRule;
  readonly reason: string;
}

function canonical(value: unknown): string {
  return JSON.stringify(value, (_key, item: unknown) => {
    if (item && typeof item === "object" && !Array.isArray(item)) {
      const sorted: Record<string, unknown> = {};
      for (const key of Object.keys(item as Record<string, unknown>).sort()) {
        sorted[key] = (item as Record<string, unknown>)[key];
      }
      return sorted;
    }
    return item;
  });
}

export function buildPolicy(
  rules: readonly PolicyRule[] = [],
  acceptMode: AcceptMode = "auto",
  allowedSenders: readonly (readonly [string, string])[] = [],
): Policy {
  const sortedSenders = [...allowedSenders].sort((a, b) => (a[0] + a[1]).localeCompare(b[0] + b[1]));
  const version = createHash("sha256")
    .update(
      canonical({
        rules: rules.map((rule) => ({
          source: rule.source,
          actor: rule.actor,
          allow: rule.allow,
          strength: rule.strength,
          note: rule.note,
        })),
        acceptMode,
        allowedSenders: sortedSenders,
      }),
    )
    .digest("hex")
    .slice(0, 12);
  return { version, rules, acceptMode, allowedSenders: sortedSenders };
}

export function senderAllowed(policy: Policy, source: string, actor: string): boolean {
  return policy.allowedSenders.some(
    ([allowedSource, allowedActor]) =>
      allowedSource === source && (allowedActor === actor || allowedActor === "*"),
  );
}

export function gate(policy: Policy | null, trigger: Trigger): GateResult {
  if (!policy) return { allowed: false, strength: "inferred", reason: "no-policy" };
  if (policy.acceptMode === "off") return { allowed: false, strength: "inferred", reason: "policy-off" };
  if (!senderAllowed(policy, trigger.source, trigger.actor)) {
    return { allowed: false, strength: "inferred", reason: "sender-not-allowed" };
  }
  for (const rule of policy.rules) {
    if (rule.source !== trigger.source) continue;
    if (rule.actor !== "*" && rule.actor !== trigger.actor) continue;
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
export function defaultPolicy(): Policy {
  return buildPolicy(
    [{ source: "local", actor: "*", allow: true, strength: "explicit", note: "local-explicit" }],
    "auto",
    [["local", "*"]],
  );
}