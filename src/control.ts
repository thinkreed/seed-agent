/**
 * Watchdog 动作接线：把判据结论落成引擎操作。
 * 规则简单到可以测试：停滞 -> 重试；投递失败 -> 重投（同样走 retry）。
 */

import type { Policy } from "./domain.ts";
import type { AnyEvent } from "./events.ts";
import type { WatchdogFinding, WatchdogReport } from "./watchdog.ts";

export type ControlAction = "retry" | "policy" | "none";

export interface WatchdogTarget {
  retry(ticketId: string): AnyEvent[];
  setPolicy(policy: Policy): AnyEvent[];
}

export interface AppliedAction {
  readonly ticketId: string;
  readonly kind: WatchdogFinding["kind"];
  readonly action: ControlAction;
}

export interface WatchdogOutcome {
  readonly findings: readonly WatchdogFinding[];
  readonly verdict: WatchdogReport["verdict"];
  readonly applied: readonly AppliedAction[];
  readonly policyApplied: boolean;
}

export class WatchdogController {
  private readonly engine: WatchdogTarget;

  constructor(engine: WatchdogTarget) {
    this.engine = engine;
  }

  /** 在线改主系统行为：只换策略，下一次 Gate 立即使用新规则。 */
  applyPolicy(policy: Policy): AnyEvent[] {
    return this.engine.setPolicy(policy);
  }

  /** 处理一次 Watchdog 报告：判据决定动作，真正的写入都经引擎。 */
  apply(report: WatchdogReport): WatchdogOutcome {
    const applied: AppliedAction[] = [];
    let policyApplied = false;
    if (report.verdict.action !== "intervene") return { ...report, applied, policyApplied };
    if (report.verdict.policy) {
      this.applyPolicy(report.verdict.policy);
      policyApplied = true;
    }

    const handled = new Set<string>();
    for (const finding of report.findings) {
      if (handled.has(finding.ticketId)) continue;
      handled.add(finding.ticketId);
      if (finding.kind === "stalled" || finding.kind === "undelivered") {
        this.engine.retry(finding.ticketId);
        applied.push({ ticketId: finding.ticketId, kind: finding.kind, action: "retry" });
      } else {
        // Source 故障由宿主重连/下一次轮询自动恢复；这里只记录已处理。
        applied.push({ ticketId: finding.ticketId, kind: finding.kind, action: "none" });
      }
    }
    return { ...report, applied, policyApplied };
  }
}