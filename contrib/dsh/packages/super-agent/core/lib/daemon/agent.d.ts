/**
 * DaemonAgent：执行环境侧。收到指令 -> 用本地执行器干活 -> 把报告作为事件推回去。
 * 自己不持有会话状态（无状态可随时重启），状态都在计算侧的 Store。
 */
import type { Clock } from "../clock.ts";
import type { DaemonEvent, DaemonRequest, DaemonResponse } from "../executor/protocol.ts";
export interface DaemonAgentOptions {
    readonly clock: Clock;
    readonly root: string;
    readonly env?: Readonly<Record<string, string>>;
    readonly emit: (event: DaemonEvent) => void;
}
export declare class DaemonAgent {
    private readonly options;
    private readonly workers;
    constructor(options: DaemonAgentOptions);
    handle(request: DaemonRequest): Promise<DaemonResponse>;
    private launch;
    private deliver;
    private stop;
    /** daemon 启动时调用：报告自己在哪些工单上还活着（用于重连恢复）。 */
    liveTickets(): string[];
}
