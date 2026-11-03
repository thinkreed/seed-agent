export function emptyState() {
    return {
        triggers: {},
        threads: {},
        tickets: {},
        evals: {},
        assignments: {},
        subscriptions: [],
        reports: {},
        inputs: {},
        attentions: {},
        messages: {},
        sentMessages: new Set(),
        messageErrors: {},
        dispositions: {},
        undelivered: new Set(),
        delivered: new Set(),
        sourceFailures: {},
        policy: null,
    };
}
export function ticketReport(state, ticketId) {
    const history = state.reports[ticketId];
    return history && history.length > 0 ? history[history.length - 1] : undefined;
}
export function subscribedTickets(state, threadId) {
    return state.subscriptions.filter((item) => item.threadId === threadId).map((item) => item.ticketId);
}
export function openAssignment(state, ticketId) {
    return Object.values(state.assignments).find((item) => item.ticketId === ticketId && item.state !== "ended");
}
//# sourceMappingURL=domain.js.map