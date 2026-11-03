/**
 * 链式召回：模型按需展开 Spill 出去的上下文。
 * 每次召回都内联下一跳的 ID，因此可以逐跳追溯：Trigger → Thread → Ticket → Thread…
 */
import { DEFAULT_BUDGET, clip } from "./context.js";
import { stageOf } from "./fsm.js";
export function recall(state, kind, id, budget = DEFAULT_BUDGET) {
    if (kind === "trigger")
        return recallTrigger(state, id, budget);
    if (kind === "thread")
        return recallThread(state, id, budget);
    return recallTicket(state, id, budget);
}
function missing(kind, id) {
    return { kind, id, found: false, summary: `${kind} not found`, text: "", handles: [] };
}
function recallTrigger(state, id, budget) {
    const trigger = state.triggers[id];
    if (!trigger)
        return missing("trigger", id);
    const tickets = Object.values(state.tickets)
        .filter((ticket) => ticket.threadIds.some((threadId) => trigger.threadIds.includes(threadId)))
        .map((ticket) => ({ kind: "ticket", id: ticket.id }));
    const handles = [
        ...trigger.threadIds.map((threadId) => ({ kind: "thread", id: threadId })),
        ...tickets,
    ];
    const clipped = clip(trigger.text, budget.inlineChars);
    return {
        kind: "trigger",
        id,
        found: true,
        summary: `${trigger.source} from ${trigger.actor} at ${trigger.at} (${clipped.chars} chars)`,
        text: clipped.text,
        handles,
    };
}
function recallThread(state, id, budget) {
    const thread = state.threads[id];
    if (!thread)
        return missing("thread", id);
    const triggers = Object.values(state.triggers)
        .filter((trigger) => trigger.threadIds.includes(id))
        .sort((a, b) => a.at - b.at || a.id.localeCompare(b.id));
    const tickets = Object.values(state.tickets).filter((ticket) => ticket.threadIds.includes(id));
    const recent = triggers.slice(-budget.maxTriggers);
    const text = recent
        .map((trigger) => `[${trigger.id}] ${trigger.actor}: ${clip(trigger.text, budget.spillChars).text}`)
        .join("\n");
    return {
        kind: "thread",
        id,
        found: true,
        summary: `thread ${id} source=${thread.source} triggers=${triggers.length} tickets=${tickets.length}`,
        text: clip(text, budget.inlineChars).text,
        handles: [
            ...recent.map((trigger) => ({ kind: "trigger", id: trigger.id })),
            ...tickets.map((ticket) => ({ kind: "ticket", id: ticket.id })),
        ],
    };
}
function recallTicket(state, id, budget) {
    const ticket = state.tickets[id];
    if (!ticket)
        return missing("ticket", id);
    const stage = stageOf(state, ticket);
    const report = (state.reports[id] ?? []).at(-1);
    const summary = `ticket ${ticket.shortName} (${ticket.id}) state=${ticket.state} stage=${stage} scope=${ticket.mandate.scope}`;
    const text = [
        `mandate: strength=${ticket.mandate.strength} policy=${ticket.mandate.policyVersion}`,
        report ? `latest report: ${report.status} — ${clip(report.summary, budget.spillChars).text}` : "no report",
    ].join("\n");
    return {
        kind: "ticket",
        id,
        found: true,
        summary,
        text: clip(text, budget.inlineChars).text,
        handles: ticket.threadIds.map((threadId) => ({ kind: "thread", id: threadId })),
    };
}
//# sourceMappingURL=recall.js.map