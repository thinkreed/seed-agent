/**
 * 上下文组织：Inline & Spill。
 *
 * 原则：窗口当 Cache 用 —— 热的 Inline 进上下文，冷的只留 ID（Spill），
 * 模型按需经 recall 工具逐跳展开（链式召回）。
 */
import { ticketReport } from "./domain.js";
import { stageOf } from "./fsm.js";
export const DEFAULT_BUDGET = {
    spillChars: 200,
    inlineChars: 2000,
    maxTriggers: 12,
    maxTickets: 6,
};
export function clip(text, limit) {
    const normalized = text.replaceAll("\r\n", "\n");
    if (normalized.length <= limit) {
        return { text: normalized, truncated: false, chars: normalized.length };
    }
    return { text: `${normalized.slice(0, limit)}…`, truncated: true, chars: normalized.length };
}
/** 由评估上下文（端口）直接构造视图：真实 LLM 评估器用这个入口。 */
export function buildView(context, budget = DEFAULT_BUDGET) {
    const batchIds = new Set(context.triggers.map((trigger) => trigger.id));
    const history = (context.history ?? []).filter((trigger) => !batchIds.has(trigger.id));
    const triggers = [...history, ...context.triggers].sort((a, b) => a.at - b.at || a.id.localeCompare(b.id));
    const inlineTriggers = triggers.slice(-budget.maxTriggers);
    const spilledIds = triggers.slice(0, Math.max(0, triggers.length - budget.maxTriggers));
    const tickets = [...context.tickets].sort((a, b) => a.id.localeCompare(b.id)).slice(0, budget.maxTickets);
    const triggerViews = inlineTriggers.map((trigger) => ({
        id: trigger.id,
        source: trigger.source,
        actor: trigger.actor,
        at: trigger.at,
        threadIds: trigger.threadIds,
        channelIds: trigger.channelIds,
        text: clip(trigger.text, budget.spillChars),
    }));
    const ticketViews = tickets.map((ticket) => ({
        id: ticket.id,
        shortName: ticket.shortName,
        state: ticket.state,
        scope: ticket.mandate.scope,
        strength: ticket.mandate.strength,
    }));
    return {
        threadId: context.threadId,
        policyVersion: context.policy?.version ?? null,
        triggers: triggerViews,
        tickets: ticketViews,
        handles: [
            { kind: "thread", id: context.threadId },
            ...inlineTriggers.map((trigger) => ({ kind: "trigger", id: trigger.id })),
            ...tickets.map((ticket) => ({ kind: "ticket", id: ticket.id })),
        ],
        spilled: spilledIds.map((trigger) => ({ kind: "trigger", id: trigger.id })),
    };
}
/** 把一批 Trigger + 线程上的工单组织成 Assessment 的可读视图。纯函数，确定性输出。 */
export function buildAssessmentView(state, threadId, budget = DEFAULT_BUDGET) {
    const triggers = Object.values(state.triggers)
        .filter((trigger) => trigger.threadIds.includes(threadId))
        .sort((a, b) => a.at - b.at || a.id.localeCompare(b.id));
    const inlineTriggers = triggers.slice(-budget.maxTriggers);
    const spilledIds = triggers.slice(0, Math.max(0, triggers.length - budget.maxTriggers));
    const triggerViews = inlineTriggers.map((trigger) => ({
        id: trigger.id,
        source: trigger.source,
        actor: trigger.actor,
        at: trigger.at,
        threadIds: trigger.threadIds,
        channelIds: trigger.channelIds,
        text: clip(trigger.text, budget.spillChars),
    }));
    const tickets = Object.values(state.tickets)
        .filter((ticket) => ticket.threadIds.includes(threadId))
        .sort((a, b) => a.id.localeCompare(b.id))
        .slice(0, budget.maxTickets);
    const ticketViews = tickets.map((ticket) => {
        const report = ticketReport(state, ticket.id);
        return {
            id: ticket.id,
            shortName: ticket.shortName,
            state: ticket.state,
            stage: stageOf(state, ticket),
            scope: ticket.mandate.scope,
            strength: ticket.mandate.strength,
            ...(report
                ? { report: { status: report.status, summary: clip(report.summary, budget.spillChars) } }
                : {}),
        };
    });
    const handles = [
        { kind: "thread", id: threadId },
        ...inlineTriggers.map((trigger) => ({ kind: "trigger", id: trigger.id })),
        ...tickets.map((ticket) => ({ kind: "ticket", id: ticket.id })),
    ];
    return {
        threadId,
        policyVersion: state.policy?.version ?? null,
        triggers: triggerViews,
        tickets: ticketViews,
        handles,
        spilled: spilledIds.map((trigger) => ({ kind: "trigger", id: trigger.id })),
    };
}
//# sourceMappingURL=context.js.map