/** 模型决策解析：把模型输出解析成 Decision，解析失败一律降级为 ignore。 */

import type { Decision, DecisionKind, Strength } from "./domain.ts";
import { extractJsonObject } from "./json.ts";

const KINDS: ReadonlySet<string> = new Set(["accept", "stop", "ignore", "unavailable"]);
const STRENGTHS: ReadonlySet<string> = new Set(["explicit", "inferred"]);

export function parseDecision(raw: string): Decision {
  const payload = extractJsonObject(raw);
  if (!payload) return fallback("no-json");
  const kind = typeof payload.kind === "string" ? payload.kind : "";
  if (!KINDS.has(kind)) return fallback(`bad-kind:${kind || "missing"}`);
  const strength: Strength =
    typeof payload.strength === "string" && STRENGTHS.has(payload.strength)
      ? (payload.strength as Strength)
      : "inferred";
  const reason = typeof payload.reason === "string" ? payload.reason.slice(0, 300) : "";
  const scope = typeof payload.scope === "string" && payload.scope ? payload.scope : "ticket";
  const rules = Array.isArray(payload.rules)
    ? payload.rules.filter((item): item is string => typeof item === "string").slice(0, 10)
    : [];
  return { kind: kind as DecisionKind, strength, reason, scope, rules };
}

function fallback(reason: string): Decision {
  return { kind: "ignore", strength: "inferred", reason: `unparsable:${reason}`, scope: "ticket", rules: [] };
}