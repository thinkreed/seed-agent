/** Watchdog 的模型裁定：把确定性 findings 交给模型判断是否需要介入。 */
import { extractJsonObject } from "./json.js";
import { watchdogSystemPrompt, watchdogUserPrompt } from "./prompts.js";
export class LlmWatchdogJudge {
    client;
    maxFindings;
    constructor(client, maxFindings = 20) {
        this.client = client;
        this.maxFindings = maxFindings;
    }
    async judge(findings, state) {
        const sample = findings.slice(0, this.maxFindings);
        const openTickets = Object.values(state.tickets)
            .filter((ticket) => ticket.state === "open")
            .map((ticket) => {
            const reports = state.reports[ticket.id] ?? [];
            const latest = reports.at(-1);
            const trigger = Object.values(state.triggers)
                .filter((item) => item.threadIds.some((threadId) => ticket.threadIds.includes(threadId)))
                .sort((a, b) => a.at - b.at)
                .at(-1);
            const assignment = Object.values(state.assignments).find((item) => item.ticketId === ticket.id && item.state !== "ended");
            return {
                id: ticket.id,
                shortName: ticket.shortName,
                latestReport: latest
                    ? { status: latest.status, summary: latest.summary.slice(0, 400), at: latest.at }
                    : null,
                request: trigger?.text.slice(0, 400) ?? "",
                assignment: assignment
                    ? { id: assignment.id, state: assignment.state, at: assignment.createdAt }
                    : null,
            };
        });
        const context = { findings: sample, openTickets };
        const raw = await this.client.complete([
            { role: "system", content: watchdogSystemPrompt() },
            { role: "user", content: watchdogUserPrompt(context) },
        ]);
        const parsed = extractJsonObject(raw);
        const action = parsed?.action === "intervene" ? "intervene" : "ok";
        const reason = typeof parsed?.reason === "string" ? parsed.reason.slice(0, 300) : "model-judged";
        return { action, reason };
    }
}
/** 自然语言运维问答：同一个外部控制回路，回答"为什么卡住/该做什么"。 */
export class LlmWatchdogAdvisor {
    client;
    constructor(client) {
        this.client = client;
    }
    async answer(question, state) {
        const context = {
            question,
            openTickets: Object.values(state.tickets)
                .filter((ticket) => ticket.state === "open")
                .map((ticket) => ({ id: ticket.id, shortName: ticket.shortName, stage: ticket.state })),
            undelivered: [...state.undelivered],
            recentReports: Object.fromEntries(Object.entries(state.reports).map(([ticketId, reports]) => [
                ticketId,
                (reports.at(-1) ?? null) && {
                    status: reports.at(-1)?.status,
                    summary: reports.at(-1)?.summary.slice(0, 300),
                },
            ])),
        };
        const raw = await this.client.complete([
            {
                role: "system",
                content: "你是主系统之外的 Watchdog 运维助手。根据状态回答维护者的问题，指出卡点与建议动作。" +
                    '只输出 JSON：{"answer":"..."}。',
            },
            { role: "user", content: JSON.stringify(context) },
        ]);
        const parsed = extractJsonObject(raw);
        if (parsed && typeof parsed.answer === "string" && parsed.answer.trim()) {
            return parsed.answer.trim().slice(0, 2000);
        }
        return raw.trim().slice(0, 2000);
    }
}
//# sourceMappingURL=watchdog_llm.js.map