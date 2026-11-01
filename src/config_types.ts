/** 配置类型：只放类型，不含解析逻辑。 */

import type { Policy } from "./domain.ts";
import type { WorkerSpec } from "./executor/protocol.ts";

export interface ModelConfig {
  readonly baseUrl: string;
  readonly apiKeyEnv: string;
  readonly name: string;
  readonly temperature?: number;
  readonly maxTokens?: number;
}

export interface GithubSourceConfig {
  readonly repos?: readonly string[];
  readonly reasons?: readonly string[];
}

export interface FeishuSourceConfig {
  readonly appIdEnv: string;
  readonly appSecretEnv: string;
  readonly chatIds: readonly string[];
}

export interface LocalSourceConfig {
  /** JSONL 收件箱：每行一个 Trigger。 */
  readonly inbox: string;
}

export interface SourcesConfig {
  readonly github?: GithubSourceConfig;
  readonly feishu?: FeishuSourceConfig;
  readonly local?: LocalSourceConfig;
}

export interface SeedConfig {
  readonly dbPath: string;
  readonly slots: number;
  readonly intervalMs: number;
  readonly staleSeconds: number;
  readonly workRoot: string;
  readonly policy: Policy;
  readonly model?: ModelConfig;
  readonly sources?: SourcesConfig;
  readonly worker?: WorkerSpec;
  readonly prepare?: WorkerSpec;
}