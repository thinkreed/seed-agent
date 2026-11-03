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
  /** 只处理最近 N 秒的消息（默认 600）。 */
  readonly sinceSeconds?: number;
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
  /** Router 形态：llm = 常驻 Router Session（批处理/记忆）；off = 单次评估器。 */
  readonly routerMode?: "llm" | "off";
  /** Router 专用模型（轻量）；缺省复用 model。 */
  readonly routerModel?: ModelConfig;
  readonly model?: ModelConfig;
  readonly sources?: SourcesConfig;
  /** 启用投机执行的 Source 白名单（空/缺省 = 关闭）。 */
  readonly speculationSources?: readonly string[];
  readonly worker?: WorkerSpec;
  readonly prepare?: WorkerSpec;
}