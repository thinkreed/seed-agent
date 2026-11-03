/**
 * Router Session（文章 §2.1）：常驻、跨 Thread 批处理、带记忆与对话历史。
 *
 * - 常驻：memory 与 history 跨批次保留；
 * - 批处理：同一轮 tick 内多个 Thread 的 assess() 合并成一次模型调用；
 * - 可召回：模型可先返回 {"recall":[...]}，由 recall() 取回下一跳再决策；
 * - 对话：chat() 承接人类消息（面板/IM），而不是把每句话都变成工单。
 *
 * 该实现同时被内核 CLI 与 DSH host 复用（host 只做转发），避免同类逻辑两处维护。
 */
import type { Decision } from "./domain.ts";
import type { AssessContext, Assessor } from "./ports.ts";
import { type RouterBatch, type RouterSessionOptions } from "./router_session_rules.ts";
export { createRouterClient, type RouterBatch, type RouterSessionOptions } from "./router_session_rules.ts";
export declare class RouterSession implements Assessor {
    private readonly client;
    private readonly state;
    private readonly budget;
    private readonly maxSteps;
    private readonly historyMessages;
    private readonly memoryChars;
    private readonly clock;
    private readonly onBatch;
    private readonly historyPath;
    private readonly pending;
    private readonly history;
    private memory;
    private scheduled;
    private lastBatch;
    constructor(options: RouterSessionOptions);
    /** 同一轮 tick 内的多个 Thread 请求在这里聚合。 */
    assess(context: AssessContext): Promise<Decision>;
    /** Router 观测所有进入系统的事件（含直通 Worker 的），只更新全局记忆，不参与路由。 */
    observe(trigger: {
        source: string;
        actor: string;
        text: string;
        threadIds: readonly string[];
    }): void;
    /** 人类消息进入 Router（面板/IM 对话）；channel 决定交互规范。 */
    chat(text: string, channel?: "im" | "async"): Promise<string>;
    /** 对话结果；work 非空时调用方应创建工单。 */
    chatResult(text: string, channel?: "im" | "async"): Promise<{
        reply: string;
        work?: string;
    }>;
    snapshot(): {
        memory: string;
        history: number;
        lastBatch: RouterBatch | undefined;
    };
    private schedule;
    private flush;
    private decide;
    private remember;
    private trimHistory;
}
