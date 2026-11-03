/** Source 健康事件：失败/恢复只追加事件，Watchdog 从状态里读取（文章 §6 基础设施故障）。 */
import type { Clock } from "./clock.ts";
import type { AnyEvent } from "./events.ts";
import type { SqliteStore } from "./store.ts";
export declare function recordSourceFailure(store: SqliteStore, clock: Clock, source: string, error: string): AnyEvent[];
export declare function recordSourceRecovery(store: SqliteStore, clock: Clock, source: string): AnyEvent[];
