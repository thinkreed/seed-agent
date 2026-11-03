/** 配置解析：校验并补默认值，错误信息带字段路径。 */

import type { AcceptMode, Policy, PolicyRule, Strength } from "./domain.ts";
import type { WorkerSpec } from "./executor/protocol.ts";
import type {
  FeishuSourceConfig,
  GithubSourceConfig,
  LocalSourceConfig,
  ModelConfig,
  SeedConfig,
  SourcesConfig,
} from "./config_types.ts";
import { buildPolicy } from "./policy.ts";
import { parseRemote } from "./config_parse_remote.ts";

export function defaultConfig(): SeedConfig {
  return {
    dbPath: "seed.db",
    slots: 4,
    intervalMs: 1000,
    staleSeconds: 1800,
    workRoot: ".seed/work",
    routerMode: "llm",
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
    workRoot: stringOr(source.workRoot, defaults.workRoot, "workRoot"),
    routerMode: routerModeOr(source.routerMode),
    ...(source.watchdogMode === undefined ? {} : { watchdogMode: watchdogModeOr(source.watchdogMode) }),
    policy: source.policy === undefined ? defaults.policy : parsePolicy(source.policy),
    ...(source.model === undefined ? {} : { model: parseModel(source.model) }),
    ...(source.routerModel === undefined ? {} : { routerModel: parseModel(source.routerModel) }),
    ...(source.sources === undefined ? {} : { sources: parseSources(source.sources) }),
    ...(source.speculationSources === undefined
      ? {}
      : { speculationSources: stringArray(source.speculationSources, "speculationSources") }),
    ...(source.worker === undefined ? {} : { worker: parseWorker(source.worker, "worker") }),
    ...(source.prepare === undefined ? {} : { prepare: parseWorker(source.prepare, "prepare") }),
    ...(source.remote === undefined ? {} : { remote: parseRemote(source.remote) }),
  };
}

function parseModel(raw: unknown): ModelConfig {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) throw new Error("model must be an object");
  const source = raw as Record<string, unknown>;
  return {
    baseUrl: requiredString(source.baseUrl, "model.baseUrl"),
    apiKeyEnv: stringOr(source.apiKeyEnv, "DEEPSEEK_API_KEY", "model.apiKeyEnv"),
    name: requiredString(source.name, "model.name"),
    ...(source.temperature === undefined ? {} : { temperature: numberOr(source.temperature, "model.temperature") }),
    ...(source.maxTokens === undefined ? {} : { maxTokens: positiveInt(source.maxTokens, 0, "model.maxTokens") }),
  };
}

function parseSources(raw: unknown): SourcesConfig {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) throw new Error("sources must be an object");
  const source = raw as Record<string, unknown>;
  return {
    ...(source.github === undefined ? {} : { github: parseGithub(source.github) }),
    ...(source.feishu === undefined ? {} : { feishu: parseFeishu(source.feishu) }),
    ...(source.local === undefined ? {} : { local: parseLocal(source.local) }),
  };
}

function parseGithub(raw: unknown): GithubSourceConfig {
  if (raw === null || typeof raw !== "object") throw new Error("sources.github must be an object");
  const source = raw as Record<string, unknown>;
  return {
    ...(source.repos === undefined ? {} : { repos: stringArray(source.repos, "sources.github.repos") }),
    ...(source.reasons === undefined ? {} : { reasons: stringArray(source.reasons, "sources.github.reasons") }),
  };
}

function parseFeishu(raw: unknown): FeishuSourceConfig {
  if (raw === null || typeof raw !== "object") throw new Error("sources.feishu must be an object");
  const source = raw as Record<string, unknown>;
  const chatIds = stringArray(source.chatIds, "sources.feishu.chatIds");
  if (chatIds.length === 0) throw new Error("sources.feishu.chatIds must not be empty");
  return {
    appIdEnv: requiredString(source.appIdEnv, "sources.feishu.appIdEnv"),
    appSecretEnv: requiredString(source.appSecretEnv, "sources.feishu.appSecretEnv"),
    chatIds,
    ...(source.sinceSeconds === undefined
      ? {}
      : { sinceSeconds: positiveInt(source.sinceSeconds, 600, "sources.feishu.sinceSeconds") }),
  };
}

function parseLocal(raw: unknown): LocalSourceConfig {
  if (raw === null || typeof raw !== "object") throw new Error("sources.local must be an object");
  const source = raw as Record<string, unknown>;
  return { inbox: requiredString(source.inbox, "sources.local.inbox") };
}

function parsePolicy(raw: unknown): Policy {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) throw new Error("policy must be an object");
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
    if (!Array.isArray(item) || item.length !== 2) {
      throw new Error(`policy.allowedSenders[${index}] must be [source, actor]`);
    }
    return [String(item[0]), String(item[1])] as const;
  });
  return buildPolicy(rules, acceptMode, allowedSenders);
}

function parseWorker(raw: unknown, field: string): WorkerSpec {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) throw new Error(`${field} must be an object`);
  const source = raw as Record<string, unknown>;
  const file = requiredString(source.file, `${field}.file`);
  const args = source.args === undefined ? [] : source.args;
  if (!Array.isArray(args) || args.some((item) => typeof item !== "string")) {
    throw new Error(`${field}.args must be string[]`);
  }
  return { file, args: args as string[] };
}

function stringArray(value: unknown, field: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`${field} must be string[]`);
  }
  return value as string[];
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

function numberOr(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${field} must be a number`);
  return value;
}

function positiveInt(value: unknown, fallback: number, field: string): number {
  if (value === undefined) return fallback;
  if (typeof value !== "number" || !Number.isInteger(value) || value <= 0) {
    throw new Error(`${field} must be a positive integer`);
  }
  return value;
}

function watchdogModeOr(value: unknown): "inline" | "external" {
  if (value === undefined) return "inline";
  if (value === "inline" || value === "external") return value;
  throw new Error("watchdogMode must be inline|external");
}

function routerModeOr(value: unknown): "llm" | "off" {
  if (value === undefined) return "llm";
  if (value === "llm" || value === "off") return value;
  throw new Error("routerMode must be llm|off");
}

function strengthOr(value: unknown, fallback: Strength, field: string): Strength {
  if (value === undefined) return fallback;
  if (value !== "explicit" && value !== "inferred") throw new Error(`${field} must be explicit|inferred`);
  return value;
}