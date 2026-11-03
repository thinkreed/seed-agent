/** 本地执行器：每个工单一个目录、一个 worker 子进程，报告经 stdout JSON 行回收。 */
import type { Clock } from "../clock.ts";
import type { Assignment, Input, Report, Ticket } from "../domain.ts";
import type { Executor } from "../ports.ts";
export interface WorkerCommand {
    readonly file: string;
    readonly args?: readonly string[];
}
export interface LocalExecutorOptions {
    /** 执行根目录：每个工单在其下用 shortName 建目录。 */
    readonly root: string;
    /** 每次 Assignment 启动的 worker 命令。 */
    readonly worker: WorkerCommand;
    /** 首次准备命令（如 git worktree），每个工单只跑一次。 */
    readonly prepare?: WorkerCommand;
    /** 报告回收：接到结构化报告后交给引擎（engine.report）。 */
    readonly report: (report: Report) => void;
    readonly clock: Clock;
    readonly env?: Readonly<Record<string, string>>;
    /** 按工单动态追加环境变量（模型配置、执行变量等）。 */
    readonly envFor?: (assignment: Assignment, ticket: Ticket, dir: string) => Record<string, string>;
    /** false = 只透传基础环境，不继承宿主全部变量（生产默认由 App 设为 false）。 */
    readonly inheritEnv?: boolean;
}
export declare class LocalExecutor implements Executor {
    private readonly options;
    private readonly children;
    private readonly prepared;
    constructor(options: LocalExecutorOptions);
    launch(assignment: Assignment, ticket: Ticket): Promise<void>;
    deliver(ticket: Ticket, input: Input): Promise<void>;
    private isLive;
    stop(assignment: Assignment): Promise<void>;
    /** 关闭所有 worker（进程退出/测试清理用）。 */
    closeAll(): void;
    private onLine;
    private environment;
}
