/**
 * WorkerSession：一个可被新消息唤醒的执行会话。
 *
 * 全双工语义：turn 进行中收到的新输入先入队，当前 turn 结束后立刻用它开下一轮，
 * 不需要等下一次外部调度。
 *
 * 后台任务完成后，结果作为一条新的会话输入（source=job）回到同一会话，
 * 由模型在下一轮消化（文章 §4.1），而不是要求模型反复轮询 status()。
 */
import type { Clock } from "./clock.ts";
import type { Report, Ticket, Trigger } from "./domain.ts";
import type { JobRegistry } from "./jobs.ts";
import type { ModelClient } from "./model.ts";
import { type ReactTool } from "./react.ts";
export interface WorkerSessionOptions {
    readonly model: ModelClient;
    readonly tools: Readonly<Record<string, ReactTool>>;
    readonly jobs: JobRegistry;
    readonly clock: Clock;
    readonly maxSteps?: number;
    readonly maxTurns?: number;
    /** 有后台任务在跑时等它完成再开下一轮（默认 true）。 */
    readonly waitForJobs?: boolean;
}
export declare class WorkerSession {
    private readonly loop;
    private readonly jobs;
    private readonly clock;
    private readonly maxTurns;
    private readonly waitForJobs;
    private readonly inbox;
    constructor(options: WorkerSessionOptions);
    /** 外部投递：turn 进行中也不会丢，进队列等当前 turn 结束。 */
    deliver(input: Trigger): void;
    get queued(): number;
    run(ticket: Ticket, initial?: readonly Trigger[]): Promise<Report[]>;
    /** 把后台任务完成通知变成一条会话输入。 */
    private jobInput;
}
