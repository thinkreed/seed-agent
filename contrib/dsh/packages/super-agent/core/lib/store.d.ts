/** 存储：append-only 事件表 + outbox + cursors（node:sqlite）。唯一写入口是 append()。 */
import type { State } from "./domain.ts";
import type { AnyEvent } from "./events.ts";
export interface OutboxItem {
    readonly id: string;
    readonly kind: string;
    readonly payload: Record<string, unknown>;
    readonly state: string;
    readonly attempts: number;
    readonly nextAt: number;
    readonly createdAt: number;
    readonly lastError: string;
}
export declare class SqliteStore {
    private readonly db;
    private cache;
    private cacheSeq;
    constructor(path?: string);
    append(event: AnyEvent): AnyEvent;
    /** 批量追加：先用当前状态逐个试跑，非法事件在落库前就抛错，避免污染历史。 */
    appendAll(events: readonly AnyEvent[]): AnyEvent[];
    events(after?: number): AnyEvent[];
    lastSeq(): number;
    state(): State;
    replayHash(): string;
    outboxEnqueue(id: string, kind: string, payload: Record<string, unknown>, at: number): void;
    outboxDue(now: number): OutboxItem[];
    outboxMark(id: string, state: string, attempts: number, nextAt: number, error?: string): void;
    outboxGet(id: string): OutboxItem | null;
    /** 是否还有未完成的 stored work（含尚未到退避时间的）。 */
    outboxHasPending(): boolean;
    /** 已有 outbox ID（重启后给 ID 工厂预热，避免撞号）。 */
    outboxIds(): string[];
    cursorGet(source: string): string | null;
    cursorSet(source: string, position: string, updatedAt: number): void;
    backupDatabase(target: string): void;
    close(): void;
}
