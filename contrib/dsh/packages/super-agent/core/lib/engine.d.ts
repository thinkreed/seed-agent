import type { Clock } from "./clock.ts";
import type { Policy, Report, State, Trigger } from "./domain.ts";
import { Effects } from "./effects.ts";
import type { AnyEvent } from "./events.ts";
import type { IdFactory } from "./ids.ts";
import type { Assessor, ChannelWriter, Executor } from "./ports.ts";
import type { SqliteStore } from "./store.ts";
export interface EngineOptions {
    store: SqliteStore;
    clock: Clock;
    ids: IdFactory;
    assessor: Assessor;
    executor: Executor;
    channels?: ChannelWriter;
    policy?: Policy | null;
    slots?: number;
}
export declare class Engine {
    readonly store: SqliteStore;
    readonly clock: Clock;
    readonly ids: IdFactory;
    readonly assessor: Assessor;
    readonly executor: Executor;
    readonly slots: number;
    readonly effects: Effects;
    readonly channels: ChannelWriter | undefined;
    private readonly evalRunner;
    private readonly actions;
    private paused;
    constructor(options: EngineOptions);
    get state(): State;
    ingest(trigger: Trigger): AnyEvent[];
    private fanOut;
    private queueEval;
    private queuedTriggerIds;
    tick(): Promise<AnyEvent[]>;
    personMessage(ticketId: string, text: string): AnyEvent[];
    pause(): void;
    resume(): void;
    get isPaused(): boolean;
    setPolicy(policy: Policy): AnyEvent[];
    retry(ticketId: string): AnyEvent[];
    recoverAfterRestart(): AnyEvent[];
    report(report: Report): AnyEvent[];
    /** Worker 取消订阅：之后同一 Thread 的事件不再直通该工单（回到 Router 评估）。 */
    unsubscribe(ticketId: string, threadId?: string): AnyEvent[];
    /** Worker 交回 Router：取消订阅并把最新事件重新入评估队列（文章 §3.2）。 */
    handback(ticketId: string, _reason?: string): AnyEvent[];
    private append;
}
