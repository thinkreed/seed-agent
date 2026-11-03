/**
 * 链式召回：模型按需展开 Spill 出去的上下文。
 * 每次召回都内联下一跳的 ID，因此可以逐跳追溯：Trigger → Thread → Ticket → Thread…
 */
import type { ContextBudget, Handle } from "./context.ts";
import type { State } from "./domain.ts";
export type RecallKind = "trigger" | "thread" | "ticket";
export interface RecallResult {
    readonly kind: RecallKind;
    readonly id: string;
    readonly found: boolean;
    readonly summary: string;
    readonly text: string;
    readonly handles: readonly Handle[];
}
export declare function recall(state: State, kind: RecallKind, id: string, budget?: ContextBudget): RecallResult;
