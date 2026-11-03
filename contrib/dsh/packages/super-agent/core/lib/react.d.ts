/**
 * 异步 ReAct 循环：耗时的工具走 start()/stop()，前台不必等待。
 *
 * 模型每一步只回一个 JSON 动作：
 *   {"action":"tool","tool":"read_file","args":{...}}
 *   {"action":"start","tool":"run_tests","args":{...}}
 *   {"action":"stop","jobId":"job-000001"}
 *   {"action":"report","status":"ready","summary":"..."}
 */
import type { Clock } from "./clock.ts";
import type { Report, ReportStatus, Ticket, Trigger } from "./domain.ts";
import type { JobNotice, JobRegistry } from "./jobs.ts";
import type { ModelClient } from "./model.ts";
export interface ReactTool {
    readonly description?: string;
    run(args: Record<string, unknown>, signal: AbortSignal): Promise<unknown>;
}
export interface ReactOptions {
    readonly model: ModelClient;
    readonly tools: Readonly<Record<string, ReactTool>>;
    readonly jobs: JobRegistry;
    readonly clock: Clock;
    readonly maxSteps?: number;
    readonly report?: (report: Report) => void;
    /** 全双工：每个推理步开始前取出当前到达的新输入（文章 §4.1）。 */
    readonly nextInputs?: () => string[];
}
type Action = {
    action: "tool";
    tool: string;
    args: Record<string, unknown>;
} | {
    action: "start";
    tool: string;
    args: Record<string, unknown>;
} | {
    action: "stop";
    jobId: string;
} | {
    action: "report";
    status: ReportStatus;
    summary: string;
};
export declare class ReactLoop {
    private readonly options;
    private readonly maxSteps;
    constructor(options: ReactOptions);
    run(ticket: Ticket, inputs: readonly Trigger[], signal?: AbortSignal): Promise<Report>;
    private injectJobNotices;
    /** 回合进行中的新输入在下一个推理步开始前注入，不必等整个回合结束。 */
    private injectNewInputs;
    private observe;
    private finish;
}
export declare function parseAction(raw: string): Action | null;
export type { JobNotice };
