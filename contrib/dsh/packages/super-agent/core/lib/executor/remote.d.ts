/**
 * RemoteExecutor：计算侧的执行器客户端。
 * 只发指令、只收报告；真正干活的是远端/本地 daemon。
 *
 * 间歇在线（文章 §5.2 BYOM）：记录已派工与未确认输入；设备重新上线后调用
 * recover() 重新拉起仍在跑的 Assignment 并补投未确认输入。
 */
import type { Clock } from "../clock.ts";
import type { Assignment, Input, Report, Ticket } from "../domain.ts";
import type { Executor } from "../ports.ts";
import type { Transport, WorkerSpec } from "./protocol.ts";
export interface RemoteExecutorOptions {
    readonly transport: Transport;
    readonly clock: Clock;
    readonly report: (report: Report) => void;
    readonly worker: WorkerSpec;
    readonly prepare?: WorkerSpec;
}
export declare class RemoteExecutor implements Executor {
    private readonly options;
    private readonly launched;
    private readonly queuedInputs;
    private readonly stopped;
    private counter;
    constructor(options: RemoteExecutorOptions);
    launch(assignment: Assignment, ticket: Ticket): Promise<void>;
    deliver(ticket: Ticket, input: Input): Promise<void>;
    stop(assignment: Assignment): Promise<void>;
    /**
     * 设备重新上线后恢复：重新拉起未结束的 Assignment，并补投未确认输入。
     * 幂等方向是"以计算侧状态为准"；daemon 侧不需要持久状态。
     */
    recover(): Promise<{
        relaunched: number;
        redelivered: number;
    }>;
    closeAll(): void;
    private launchRequest;
    private deliverRequest;
    private send;
    private onEvent;
}
