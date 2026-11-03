/**
 * SourceRunner：把 Source 的 poll 结果喂进引擎，并逐源记录位点与失败。
 * 一个 Source 出错不影响其它 Source（隔离）。
 */
import type { Clock } from "./clock.ts";
import type { Engine } from "./engine.ts";
import type { Source } from "./ports.ts";
import type { SqliteStore } from "./store.ts";
export interface SourceFailure {
    readonly source: string;
    readonly error: string;
}
export interface PollReport {
    readonly ingested: number;
    readonly failures: readonly SourceFailure[];
}
export declare class SourceRunner {
    private readonly sources;
    private readonly engine;
    private readonly store;
    private readonly clock;
    private readonly failed;
    private readonly onTrigger;
    private readonly onIngested;
    constructor(options: {
        sources: readonly Source[];
        engine: Engine;
        store: SqliteStore;
        clock: Clock;
        /** 观测回调：Router 用它看到所有事件（含随后直通 Worker 的）。 */
        onTrigger?: (trigger: import("./domain.ts").Trigger) => void;
        /** 新事件完成入账后的回调（投机执行只对真正的新事件触发一次）。 */
        onIngested?: (trigger: import("./domain.ts").Trigger) => void;
    });
    /** 轮询所有 Source：各自独立容错。 */
    pollOnce(): Promise<PollReport>;
    /** 轮询直到所有 Source 都没有新事件。失败按来源去重（保留最后一次错误）。 */
    drain(maxRounds?: number): Promise<PollReport>;
}
