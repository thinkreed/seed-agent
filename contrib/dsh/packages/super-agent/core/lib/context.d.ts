/**
 * 上下文组织：Inline & Spill。
 *
 * 原则：窗口当 Cache 用 —— 热的 Inline 进上下文，冷的只留 ID（Spill），
 * 模型按需经 recall 工具逐跳展开（链式召回）。
 */
import type { State } from "./domain.ts";
import type { AssessContext } from "./ports.ts";
export interface ContextBudget {
    /** 单个对象最多内联多少字符（超过即 Spill）。 */
    readonly spillChars: number;
    /** 单次召回最多返回多少字符。 */
    readonly inlineChars: number;
    /** 一批最多内联多少条 Trigger。 */
    readonly maxTriggers: number;
    /** 最多内联多少张工单。 */
    readonly maxTickets: number;
}
export declare const DEFAULT_BUDGET: ContextBudget;
export interface Handle {
    readonly kind: "trigger" | "thread" | "ticket";
    readonly id: string;
}
export interface InlineText {
    readonly text: string;
    readonly truncated: boolean;
    readonly chars: number;
}
export interface TriggerView {
    readonly id: string;
    readonly source: string;
    readonly actor: string;
    readonly at: number;
    readonly threadIds: readonly string[];
    readonly channelIds: readonly string[];
    readonly text: InlineText;
}
export interface TicketView {
    readonly id: string;
    readonly shortName: string;
    readonly state: string;
    readonly stage?: string;
    readonly scope: string;
    readonly strength: string;
    readonly report?: {
        readonly status: string;
        readonly summary: InlineText;
    };
}
export interface AssessmentView {
    readonly threadId: string;
    readonly policyVersion: string | null;
    readonly triggers: readonly TriggerView[];
    readonly tickets: readonly TicketView[];
    readonly handles: readonly Handle[];
    readonly spilled: readonly Handle[];
}
export declare function clip(text: string, limit: number): InlineText;
/** 由评估上下文（端口）直接构造视图：真实 LLM 评估器用这个入口。 */
export declare function buildView(context: AssessContext, budget?: ContextBudget): AssessmentView;
/** 把一批 Trigger + 线程上的工单组织成 Assessment 的可读视图。纯函数，确定性输出。 */
export declare function buildAssessmentView(state: State, threadId: string, budget?: ContextBudget): AssessmentView;
