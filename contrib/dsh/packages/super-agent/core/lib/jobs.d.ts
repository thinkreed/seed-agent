/**
 * 后台任务注册表：异步 ReAct 的底座。
 *
 * - start() 立即返回 jobId，任务在后台跑；
 * - 完成/失败/超时都会留下记录与待消费通知；
 * - stop() 通过 AbortSignal 协作取消；
 * - tick() 负责把超过时限的任务判死（默认 30 分钟）。
 */
import type { Clock } from "./clock.ts";
export type JobState = "running" | "done" | "failed" | "stopped";
export interface JobRecord {
    readonly id: string;
    readonly kind: string;
    readonly ticketId: string;
    readonly state: JobState;
    readonly startedAt: number;
    finishedAt?: number;
    result?: unknown;
    error?: string;
}
export interface JobNotice {
    readonly jobId: string;
    readonly ticketId: string;
    readonly state: JobState;
    readonly result?: unknown;
    readonly error?: string;
}
export declare class JobRegistry {
    private readonly clock;
    private readonly maxRunSeconds;
    private readonly jobs;
    private readonly notices;
    private readonly waiters;
    private counter;
    constructor(clock: Clock, options?: {
        maxRunSeconds?: number;
    });
    start(kind: string, ticketId: string, run: (signal: AbortSignal) => Promise<unknown>): string;
    stop(id: string): boolean;
    /** 把超时未完成的任务判死。 */
    tick(): void;
    get(id: string): JobRecord | undefined;
    running(): JobRecord[];
    /** 某个工单仍在后台运行的任务。 */
    runningFor(ticketId: string): JobRecord[];
    hasPending(ticketId: string): boolean;
    /**
     * 等待该工单的下一条完成通知（文章 §4.1：结果作为新事件回到会话）。
     * 没有待消费通知且没有在跑任务时返回 undefined，避免空等。
     */
    nextNotice(ticketId: string): Promise<JobNotice | undefined>;
    /** 取走尚未消费的完成通知（供 ReAct 循环注入 observation）。 */
    drainNotices(): JobNotice[];
    private settle;
    private deadlineTimer;
}
