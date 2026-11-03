/**
 * Watchdog：主系统之外的独立控制回路。
 * 先做确定性判据（停滞、投递失败），再交给模型判断是否需要介入。
 */
export class Watchdog {
    clock;
    staleSeconds;
    judge;
    advisor;
    constructor(options) {
        this.clock = options.clock;
        this.staleSeconds = options.staleSeconds ?? 1800;
        this.judge = options.judge;
        this.advisor = options.advisor;
    }
    async check(state) {
        const findings = this.findings(state);
        const active = Object.values(state.tickets).some((ticket) => ticket.state === "open");
        if (findings.length === 0 && !active) {
            return { findings, verdict: { action: "ok", reason: "quiet" } };
        }
        if (!this.judge) {
            return {
                findings,
                verdict: findings.length > 0
                    ? { action: "intervene", reason: "deterministic-findings" }
                    : { action: "ok", reason: "active-without-deterministic-findings" },
            };
        }
        // 有在跑工单时也让模型看"是否真的在推进/是否跑偏"，而不是只看停滞阈值。
        return { findings, verdict: await this.judge.judge(findings, state) };
    }
    /** 自然语言问它"为什么卡住/哪里有问题"；未接模型时给出确定性摘要。 */
    async ask(question, state) {
        if (this.advisor)
            return this.advisor.answer(question, state);
        return deterministicAnswer(question, state, this.findings(state));
    }
    findings(state) {
        const now = this.clock.now();
        const collected = [];
        for (const [source, error] of Object.entries(state.sourceFailures)) {
            collected.push({
                kind: "source",
                ticketId: "",
                detail: `source ${source} failed: ${error}`,
            });
        }
        for (const inputId of state.undelivered) {
            const input = state.inputs[inputId];
            if (!input)
                continue;
            collected.push({
                kind: "undelivered",
                ticketId: input.ticketId,
                detail: `input ${inputId} failed to reach its executor`,
            });
        }
        for (const ticket of Object.values(state.tickets)) {
            if (ticket.state !== "open")
                continue;
            const last = lastActivity(state, ticket.id) ?? ticket.createdAt;
            if (now - last >= this.staleSeconds) {
                collected.push({
                    kind: "stalled",
                    ticketId: ticket.id,
                    detail: `no activity for ${Math.round(now - last)}s`,
                });
            }
        }
        return collected;
    }
}
function lastActivity(state, ticketId) {
    const times = [];
    for (const assignment of Object.values(state.assignments)) {
        if (assignment.ticketId === ticketId)
            times.push(assignment.createdAt);
    }
    for (const input of Object.values(state.inputs)) {
        if (input.ticketId === ticketId)
            times.push(input.at);
    }
    for (const report of state.reports[ticketId] ?? [])
        times.push(report.at);
    return times.length > 0 ? Math.max(...times) : undefined;
}
/** 无模型时的确定性运维回答：把状态与判据讲清楚。 */
function deterministicAnswer(question, state, findings) {
    const open = Object.values(state.tickets).filter((ticket) => ticket.state === "open");
    const undelivered = state.undelivered.size;
    const lines = [
        `问题：${question}`,
        `open 工单 ${open.length} 个：${open.map((ticket) => `${ticket.shortName}(${ticket.id})`).join(", ") || "无"}`,
        `未投递输入：${undelivered}`,
        `异常：${findings.length} 项${findings.length > 0 ? " — " + findings.map((item) => `${item.kind}:${item.ticketId}`).join("; ") : ""}`,
    ];
    for (const finding of findings.slice(0, 5))
        lines.push(`- ${finding.ticketId}: ${finding.detail}`);
    lines.push(findings.length === 0
        ? "结论：未发现停滞或投递失败；如果仍觉得慢，请提供工单 ID。"
        : "结论：存在需要介入的项；可 retry 对应工单或检查执行器/daemon。");
    return lines.join("\n");
}
//# sourceMappingURL=watchdog.js.map