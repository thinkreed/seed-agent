/**
 * Watchdog 动作接线：把判据结论落成引擎操作。
 * 规则简单到可以测试：停滞 -> 重试；投递失败 -> 重投（同样走 retry）。
 */
import type { Engine } from "./engine.ts";
import type { Policy } from "./domain.ts";
import type { AnyEvent } from "./events.ts";
import type { WatchdogFinding, WatchdogReport } from "./watchdog.ts";
export type ControlAction = "retry" | "none";
export interface AppliedAction {
    readonly ticketId: string;
    readonly kind: WatchdogFinding["kind"];
    readonly action: ControlAction;
}
export interface WatchdogOutcome {
    readonly findings: readonly WatchdogFinding[];
    readonly verdict: WatchdogReport["verdict"];
    readonly applied: readonly AppliedAction[];
}
export declare class WatchdogController {
    private readonly engine;
    constructor(engine: Engine);
    /** 在线改主系统行为：只换策略，下一次 Gate 立即使用新规则。 */
    applyPolicy(policy: Policy): AnyEvent[];
    /** 处理一次 Watchdog 报告：判据决定动作，真正的写入都经引擎。 */
    apply(report: WatchdogReport): WatchdogOutcome;
}
