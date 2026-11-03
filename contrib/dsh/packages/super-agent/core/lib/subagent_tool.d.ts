/**
 * Worker 内部的 Subagent 工具（文章 §2.2：Worker 可再创建 Subagent 执行子任务）。
 *
 * 子任务跑在独立上下文里，但共享模型、工具与后台任务注册表；
 * 递归 spawn 被过滤，避免无限套娃。返回结构化报告，由父 Worker 决定如何汇报。
 */
import type { Clock } from "./clock.ts";
import type { Ticket } from "./domain.ts";
import type { JobRegistry } from "./jobs.ts";
import type { ModelClient } from "./model.ts";
import { type ReactTool } from "./react.ts";
export interface SubagentToolOptions {
    readonly model: ModelClient;
    readonly tools: Readonly<Record<string, ReactTool>>;
    readonly jobs: JobRegistry;
    readonly clock: Clock;
    readonly ticket: Ticket;
    readonly maxSteps?: number;
}
export declare function subagentTool(options: SubagentToolOptions): ReactTool;
