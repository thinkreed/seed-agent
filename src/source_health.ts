/** Source 健康事件：失败/恢复只追加事件，Watchdog 从状态里读取（文章 §6 基础设施故障）。 */

import type { Clock } from "./clock.ts";
import { ev } from "./builders.ts";
import type { AnyEvent } from "./events.ts";
import type { SqliteStore } from "./store.ts";

export function recordSourceFailure(
  store: SqliteStore,
  clock: Clock,
  source: string,
  error: string,
): AnyEvent[] {
  return store.appendAll([ev.sourceFailed(source, error.slice(0, 400), clock.now())]);
}

export function recordSourceRecovery(
  store: SqliteStore,
  clock: Clock,
  source: string,
): AnyEvent[] {
  return store.appendAll([ev.sourceRecovered(source, clock.now())]);
}