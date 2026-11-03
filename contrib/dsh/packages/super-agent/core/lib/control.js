/**
 * Watchdog 动作接线：把判据结论落成引擎操作。
 * 规则简单到可以测试：停滞 -> 重试；投递失败 -> 重投（同样走 retry）。
 */
export class WatchdogController {
    engine;
    constructor(engine) {
        this.engine = engine;
    }
    /** 在线改主系统行为：只换策略，下一次 Gate 立即使用新规则。 */
    applyPolicy(policy) {
        return this.engine.setPolicy(policy);
    }
    /** 处理一次 Watchdog 报告：判据决定动作，真正的写入都经引擎。 */
    apply(report) {
        const applied = [];
        if (report.verdict.action !== "intervene")
            return { ...report, applied };
        const handled = new Set();
        for (const finding of report.findings) {
            if (handled.has(finding.ticketId))
                continue;
            handled.add(finding.ticketId);
            if (finding.kind === "stalled" || finding.kind === "undelivered") {
                this.engine.retry(finding.ticketId);
                applied.push({ ticketId: finding.ticketId, kind: finding.kind, action: "retry" });
            }
            else {
                // Source 故障由宿主重连/下一次轮询自动恢复；这里只记录已处理。
                applied.push({ ticketId: finding.ticketId, kind: finding.kind, action: "none" });
            }
        }
        return { ...report, applied };
    }
}
//# sourceMappingURL=control.js.map