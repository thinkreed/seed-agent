/** 模型客户端工厂：Router 与 Worker 可用不同模型（文章 §2.1：Router 可轻量）。 */

import type { ModelConfig } from "./config_types.ts";
import { OpenAIClient } from "./llm/openai.ts";

export function createModelClient(config: ModelConfig, apiKey: string): OpenAIClient {
  return new OpenAIClient({
    baseUrl: config.baseUrl,
    apiKey,
    model: config.name,
    ...(config.temperature === undefined ? {} : { temperature: config.temperature }),
    ...(config.maxTokens === undefined ? {} : { maxTokens: config.maxTokens }),
  });
}