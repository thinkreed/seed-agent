/** 提示词：唯一的"模型侧策略"落点（改行为先改这里，不改引擎）。 */
import type { AssessmentView } from "./context.ts";
import type { Ticket, Trigger } from "./domain.ts";
/** Assessment（Slow Path）：把一批 Trigger 判成 accept / stop / ignore / unavailable。 */
export declare function assessmentSystemPrompt(): string;
export declare function assessmentUserPrompt(view: AssessmentView): string;
/** Worker（执行会话）：只做一件被授权的事，并把结果结构化回报。 */
export declare function workerSystemPrompt(ticket: Ticket, inputs: readonly Trigger[], tools?: readonly {
    name: string;
    description: string;
}[]): string;
/** Router（主会话）：只接人、分派、对外回复，不亲自执行具体任务。 */
export declare function routerSystemPrompt(): string;
/** Watchdog：判断系统是否真的在推进，是否要介入。 */
export declare function watchdogSystemPrompt(): string;
export declare function watchdogUserPrompt(context: unknown): string;
