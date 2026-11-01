/**
 * Watchdog 动作接线：把判据结论落成引擎操作。
 * 规则简单到可以测试：停滞 -> 重试；投递失败 -> 重投（同样走 retry）。
 */

import type { Engine } from "./engine.ts";
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

export class WatchdogController {
  private readonly engine: Engine;

  constructor(engine: Engine) {
    this.engine = engine;
  }

  /** 处理一次 Watchdog 报告：判据决定动作，真正的写入都经引擎。 */
  apply(report: WatchdogReport): WatchdogOutcome {
    const applied: AppliedAction[] = [];
    if (report.verdict.action !== "intervene") return { ...report, applied };

    const handled = new Set<string>();
    for (const finding of report.findings) {
      if (handled.has(finding.ticketId)) continue;
      handled.add(finding.ticketId);
      if (finding.kind === "stalled" || finding.kind === "undelivered") {
        this.engine.retry(finding.ticketId);
        applied.push({ ticketId: finding.ticketId, kind: finding.kind, action: "retry" });
      }
    }
    return { ...report, applied };
  }
}