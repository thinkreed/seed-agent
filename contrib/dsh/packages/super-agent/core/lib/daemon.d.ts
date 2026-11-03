/**
 * Daemon：进程内的主循环 —— 轮询 Source、驱动引擎、执行副作用。
 * 与"存算分离"对应：状态在 Store，循环本身无状态，可随时重启。
 */
import type { Clock } from "./clock.ts";
import type { Engine } from "./engine.ts";
import type { SourceRunner } from "./runner.ts";
import type { SqliteStore } from "./store.ts";
export interface RoundReport {
    readonly ingested: number;
    readonly events: number;
    readonly failures: number;
}
export interface WatchdogBridge {
    check(state: import("./domain.ts").State): Promise<import("./watchdog.ts").WatchdogReport>;
    apply(report: import("./watchdog.ts").WatchdogReport): unknown;
}
export interface DaemonOptions {
    readonly runner: SourceRunner;
    readonly engine: Engine;
    readonly store: SqliteStore;
    readonly clock: Clock;
    readonly intervalMs?: number;
    readonly sleep?: (ms: number) => Promise<void>;
    readonly watchdog?: WatchdogBridge;
    /** Watchdog 巡检间隔（毫秒，默认 60000）；避免每轮都调用模型。 */
    readonly watchdogIntervalMs?: number;
    readonly afterRound?: () => void | Promise<void>;
}
export declare class Daemon {
    private readonly options;
    private running;
    private rounds;
    private lastWatchdogAt;
    constructor(options: DaemonOptions);
    /** 跑一轮：收事件 -> 驱动引擎 -> 巡检。返回这一轮的统计。 */
    runRound(): Promise<RoundReport>;
    /** 常驻循环，直到 stop()。 */
    run(maxRounds?: number): Promise<number>;
    stop(): void;
    get roundCount(): number;
}
