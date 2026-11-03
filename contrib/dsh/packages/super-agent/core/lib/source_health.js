/** Source 健康事件：失败/恢复只追加事件，Watchdog 从状态里读取（文章 §6 基础设施故障）。 */
import { ev } from "./builders.js";
export function recordSourceFailure(store, clock, source, error) {
    return store.appendAll([ev.sourceFailed(source, error.slice(0, 400), clock.now())]);
}
export function recordSourceRecovery(store, clock, source) {
    return store.appendAll([ev.sourceRecovered(source, clock.now())]);
}
//# sourceMappingURL=source_health.js.map