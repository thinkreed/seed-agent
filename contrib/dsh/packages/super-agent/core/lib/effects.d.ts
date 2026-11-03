/** stored work：先落库、后执行、失败退避。副作用只能从这里出去。 */
import type { Clock } from "./clock.ts";
import type { AnyEvent } from "./events.ts";
import type { OutboxItem, SqliteStore } from "./store.ts";
export interface Backoff {
    readonly schedule: readonly number[];
    readonly maxAttempts: number;
}
export declare const DEFAULT_BACKOFF: Backoff;
export type EffectHandler = (item: OutboxItem) => AnyEvent[] | Promise<AnyEvent[]>;
export declare function backoffDelay(backoff: Backoff, attempts: number): number;
export declare class Effects {
    private readonly handlers;
    private readonly store;
    private readonly clock;
    private readonly backoff;
    constructor(store: SqliteStore, clock: Clock, handlers?: Record<string, EffectHandler>, backoff?: Backoff);
    register(kind: string, handler: EffectHandler): void;
    enqueue(id: string, kind: string, payload: Record<string, unknown>, at?: number): string;
    /** 执行所有到期项，返回 (产生的事件, 被丢弃的 id)。 */
    drain(): Promise<{
        produced: AnyEvent[];
        dropped: string[];
    }>;
}
