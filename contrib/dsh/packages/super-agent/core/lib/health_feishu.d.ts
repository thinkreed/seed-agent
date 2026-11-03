/** 飞书相关健康检查（token + 群里是否可见）。 */
import type { SeedConfig } from "./config_types.ts";
import type { CheckDeps, Checker } from "./health.ts";
export declare function feishuCheckers(config: SeedConfig, deps: CheckDeps): Checker[];
