/** 配置入口：类型、默认值、加载。解析实现见 config_parse.ts。 */
import { defaultConfig, parseConfig } from "./config_parse.ts";
import type { SeedConfig } from "./config_types.ts";
export { defaultConfig, parseConfig };
export type { FeishuSourceConfig, GithubSourceConfig, LocalSourceConfig, ModelConfig, SeedConfig, SourcesConfig, } from "./config_types.ts";
export declare function loadConfig(path?: string): SeedConfig;
