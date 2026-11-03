/**
 * OpenAI 兼容客户端（DeepSeek / 百炼 / 任何 /chat/completions 兼容端点）。
 * 真实 HTTP，无 mock 分支；超时、限流重试都在这里。
 */
import type { ModelClient, ModelMessage } from "../model.ts";
export interface OpenAIClientOptions {
    readonly baseUrl: string;
    readonly apiKey: string;
    readonly model: string;
    readonly temperature?: number;
    readonly timeoutMs?: number;
    readonly maxRetries?: number;
    readonly maxTokens?: number;
}
export interface OpenAICacheStats {
    readonly requests: number;
    readonly promptTokens: number;
    readonly cachedTokens: number;
    readonly uncachedTokens: number;
    readonly hitRate: number;
}
export declare class OpenAIClient implements ModelClient {
    private readonly options;
    private requests;
    private promptTokens;
    private cachedTokens;
    private uncachedTokens;
    constructor(options: OpenAIClientOptions);
    complete(messages: readonly ModelMessage[]): Promise<string>;
    /** 最近一次请求以来的 provider 缓存统计（DeepSeek/Bailian 返回 usage 时可用）。 */
    cacheStats(): OpenAICacheStats;
    private recordUsage;
    private once;
}
