/** 配置：单一入口，文件 + 默认值 + 校验。 */

import { readFileSync } from "node:fs";

import type { AcceptMode, Policy, PolicyRule, Strength } from "./domain.ts";
import type { WorkerSpec } from "./executor/protocol.ts";
import { buildPolicy } from "./policy.ts";

export interface SeedConfig {
  readonly dbPath: string;
  readonly slots: number;
  readonly intervalMs: number;
  readonly staleSeconds: number;
  readonly policy: Policy;
  readonly worker?: WorkerSpec;
  readonly prepare?: WorkerSpec;
}

export function defaultConfig(): SeedConfig {
  return {
    dbPath: "seed.db",
    slots: 4,
    intervalMs: 1000,
    staleSeconds: 1800,
    policy: buildPolicy(
      [{ source: "local", actor: "*", allow: true, strength: "explicit", note: "local-explicit" }],
      "auto",
      [["local", "*"]],
    ),
  };
}

export function parseConfig(raw: unknown): SeedConfig {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("config must be a JSON object");
  }
  const source = raw as Record<string, unknown>;
  const defaults = defaultConfig();
  return {
    dbPath: stringOr(source.dbPath, defaults.dbPath, "dbPath"),
    slots: positiveInt(source.slots, defaults.slots, "slots"),
    intervalMs: positiveInt(source.intervalMs, defaults.intervalMs, "intervalMs"),
    staleSeconds: positiveInt(source.staleSeconds, defaults.staleSeconds, "staleSeconds"),
    policy: source.policy === undefined ? defaults.policy : parsePolicy(source.policy),
    ...(source.worker === undefined ? {} : { worker: parseWorker(source.worker, "worker") }),
    ...(source.prepare === undefined ? {} : { prepare: parseWorker(source.prepare, "prepare") }),
  };
}

export function loadConfig(path?: string): SeedConfig {
  if (!path) return defaultConfig();
  return parseConfig(JSON.parse(readFileSync(path, "utf8")));
}

function parsePolicy(raw: unknown): Policy {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("policy must be an object");
  }
  const source = raw as Record<string, unknown>;
  const rulesRaw = source.rules ?? [];
  if (!Array.isArray(rulesRaw)) throw new Error("policy.rules must be an array");
  const rules: PolicyRule[] = rulesRaw.map((item, index) => {
    if (item === null || typeof item !== "object") throw new Error(`policy.rules[${index}] must be an object`);
    const rule = item as Record<string, unknown>;
    return {
      source: requiredString(rule.source, `policy.rules[${index}].source`),
      actor: stringOr(rule.actor, "*", `policy.rules[${index}].actor`),
      allow: booleanOr(rule.allow, false, `policy.rules[${index}].allow`),
      strength: strengthOr(rule.strength, "inferred", `policy.rules[${index}].strength`),
      note: stringOr(rule.note, "", `policy.rules[${index}].note`),
    };
  });
  const acceptMode = (source.acceptMode ?? "auto") as AcceptMode;
  if (!["auto", "record", "off"].includes(acceptMode)) throw new Error(`bad policy.acceptMode: ${acceptMode}`);
  const sendersRaw = source.allowedSenders ?? [];
  if (!Array.isArray(sendersRaw)) throw new Error("policy.allowedSenders must be an array");
  const allowedSenders = sendersRaw.map((item, index) => {
    if (!Array.isArray(item) || item.length !== 2) throw new Error(`policy.allowedSenders[${index}] must be [source, actor]`);
    return [String(item[0]), String(item[1])] as const;
  });
  return buildPolicy(rules, acceptMode, allowedSenders);
}

function parseWorker(raw: unknown, field: string): WorkerSpec {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) throw new Error(`${field} must be an object`);
  const source = raw as Record<string, unknown>;
  const file = stringOr(source.file, "", `${field}.file`);
  if (!file) throw new Error(`${field}.file is required`);
  const args = source.args === undefined ? [] : source.args;
  if (!Array.isArray(args) || args.some((item) => typeof item !== "string")) {
    throw new Error(`${field}.args must be string[]`);
  }
  return { file, args: args as string[] };
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${field} must be a non-empty string`);
  }
  return value;
}

function stringOr(value: unknown, fallback: string, field: string): string {
  if (value === undefined) return fallback;
  if (typeof value !== "string") throw new Error(`${field} must be a string`);
  return value;
}

function booleanOr(value: unknown, fallback: boolean, field: string): boolean {
  if (value === undefined) return fallback;
  if (typeof value !== "boolean") throw new Error(`${field} must be a boolean`);
  return value;
}

function positiveInt(value: unknown, fallback: number, field: string): number {
  if (value === undefined) return fallback;
  if (typeof value !== "number" || !Number.isInteger(value) || value <= 0) {
    throw new Error(`${field} must be a positive integer`);
  }
  return value;
}

function strengthOr(value: unknown, fallback: Strength, field: string): Strength {
  if (value === undefined) return fallback;
  if (value !== "explicit" && value !== "inferred") throw new Error(`${field} must be explicit|inferred`);
  return value;
}