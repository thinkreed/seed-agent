/** 状态里已出现过的所有 ID（给 SeqIds 预热用）。 */
export function stateIds(state) {
    const ids = [];
    for (const group of [
        state.triggers,
        state.threads,
        state.tickets,
        state.evals,
        state.assignments,
        state.inputs,
        state.attentions,
        state.messages,
        state.dispositions,
    ]) {
        ids.push(...Object.keys(group));
    }
    for (const subscription of state.subscriptions) {
        ids.push(subscription.ticketId, subscription.threadId);
    }
    return ids;
}
//# sourceMappingURL=state_ids.js.map