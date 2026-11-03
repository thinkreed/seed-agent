/** 配置解析：校验并补默认值，错误信息带字段路径。 */
import type { SeedConfig } from "./config_types.ts";
export declare function defaultConfig(): SeedConfig;
export declare function parseConfig(raw: unknown): SeedConfig;
