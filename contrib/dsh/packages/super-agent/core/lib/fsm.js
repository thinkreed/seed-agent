/** 工单阶段派生与合法转换检查。阶段只从 State 计算，绝不落库。 */
import { openAssignment, ticketReport } from "./domain.js";
export class TransitionError extends Error {
    constructor(message) {
        super(message);
        this.name = "TransitionError";
    }
}
const PERSON_STAGES = new Set([
    "person/delivery",
    "person/answer",
    "person/review",
    "person/blocked",
    "person/failed",
]);
export function stageOf(state, ticket) {
    if (ticket.state === "ended")
        return "idle";
    const report = ticketReport(state, ticket.id);
    if (isUndelivered(state, ticket.id))
        return "person/delivery";
    if (state.attentions[ticket.id])
        return "person/answer";
    if (report?.status === "ready")
        return "person/review";
    if (report?.status === "blocked" && !personSpokeAfter(state, ticket.id, report.at)) {
        return "person/blocked";
    }
    if (report?.status === "failed" && !personSpokeAfter(state, ticket.id, report.at)) {
        return "person/failed";
    }
    if (report?.status === "waiting")
        return "idle";
    const assignment = openAssignment(state, ticket.id);
    if (!assignment)
        return hasEndedAssignment(state, ticket.id) ? "idle" : "working/queued";
    if (assignment.state === "pending")
        return "working/queued";
    return "working";
}
export function requiresPerson(stage) {
    return PERSON_STAGES.has(stage);
}
export function assertCanEnd(ticket, reason = "") {
    if (ticket.state === "ended")
        throw new TransitionError(`ticket ${ticket.id} already ended`);
    if (ticket.stopped && reason !== "stopped") {
        throw new TransitionError(`ticket ${ticket.id} was stopped by a person`);
    }
}
function hasEndedAssignment(state, ticketId) {
    return Object.values(state.assignments).some((item) => item.ticketId === ticketId && item.state === "ended");
}
function isUndelivered(state, ticketId) {
    for (const inputId of state.undelivered) {
        const input = state.inputs[inputId];
        if (input && input.ticketId === ticketId)
            return true;
    }
    return false;
}
function personSpokeAfter(state, ticketId, at) {
    return Object.values(state.inputs).some((input) => input.ticketId === ticketId && input.kind === "text" && input.at > at);
}
//# sourceMappingURL=fsm.js.map