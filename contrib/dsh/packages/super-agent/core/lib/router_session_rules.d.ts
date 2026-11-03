/** Router Session 的提示词规则与客户端工厂（与状态机分离，便于复用/测试）。 */
import type { ContextBudget } from "./context.ts";
import type { State } from "./domain.ts";
import type { ModelClient } from "./model.ts";
export interface RouterBatch {
    readonly threads: number;
    readonly triggers: number;
    readonly at: number;
}
export interface RouterSessionOptions {
    readonly client: ModelClient;
    readonly state: () => State;
    readonly budget?: ContextBudget;
    readonly maxSteps?: number;
    readonly historyMessages?: number;
    readonly memoryChars?: number;
    readonly clock?: import("./clock.ts").Clock;
    readonly onBatch?: (batch: RouterBatch) => void;
    /** Router 对话历史的落盘路径；缺省只保存在内存。 */
    readonly historyPath?: string;
}
export declare const ROUTER_ACCEPT_RULES: string;
export declare const ROUTER_CHAT_RULES: string;
/** 信道定制的交互规范（文章 §4.2）：IM 低打扰，异步信道结构化。 */
export declare function channelChatRules(channel: "im" | "async"): string;
/** 用配置构造 OpenAI 兼容客户端的便捷工厂。 */
export declare function createRouterClient(options: {
    baseUrl: string;
    apiKey: string;
    model: string;
    timeoutMs: number;
}): ModelClient;
