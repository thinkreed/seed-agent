/** 运行时装配：唯一把端口接到引擎上的地方。 */
import type { Clock } from "./clock.ts";
import type { Policy } from "./domain.ts";
import { Engine } from "./engine.ts";
import type { IdFactory } from "./ids.ts";
import type { Assessor, ChannelWriter, Executor } from "./ports.ts";
import { SqliteStore } from "./store.ts";
export interface RuntimeConfig {
    readonly dbPath?: string;
    readonly slots?: number;
    readonly policy?: Policy;
    readonly channels?: ChannelWriter;
}
export interface RuntimeOptions {
    readonly assessor: Assessor;
    readonly executor: Executor;
    readonly config?: RuntimeConfig;
    readonly clock?: Clock;
    readonly ids?: IdFactory;
}
export declare class Runtime {
    readonly engine: Engine;
    readonly store: SqliteStore;
    readonly clock: Clock;
    readonly config: RuntimeConfig;
    constructor(engine: Engine, store: SqliteStore, clock: Clock, config: RuntimeConfig);
    static build(options: RuntimeOptions): Runtime;
    /** 跑到没有新事件为止；返回 tick 次数。 */
    tickUntilIdle(maxTicks?: number): Promise<number>;
    /** 没有在跑的 assignment、没有排队 Eval、没有待执行副作用。 */
    isSettled(): boolean;
    close(): void;
}
