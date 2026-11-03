/**
 * 事件信封与类型表。
 * 新增事件 = 这里加一行类型 + reducer.ts 加一个分支（architecture 测试会校验）。
 */
export const EVENT_TYPES = Object.keys({
    "trigger.recorded": 1,
    "thread.declared": 1,
    "trigger.filtered": 1,
    "disposition.recorded": 1,
    "eval.queued": 1,
    "eval.started": 1,
    "eval.decided": 1,
    "ticket.opened": 1,
    "ticket.ended": 1,
    "ticket.resumed": 1,
    "subscription.added": 1,
    "subscription.removed": 1,
    "assignment.created": 1,
    "assignment.started": 1,
    "assignment.ended": 1,
    "input.fanned_out": 1,
    "input.delivered": 1,
    "input.undelivered": 1,
    "report.recorded": 1,
    "attention.opened": 1,
    "message.queued": 1,
    "message.sent": 1,
    "message.failed": 1,
    "source.failed": 1,
    "source.recovered": 1,
    "policy.changed": 1,
});
/** 必填载荷字段：入账前校验，防止半成品事件。 */
export const REQUIRED_KEYS = {
    "trigger.recorded": ["trigger"],
    "thread.declared": ["thread"],
    "trigger.filtered": ["triggerId", "layer", "reason"],
    "disposition.recorded": ["triggerId", "disposition"],
    "eval.queued": ["eval"],
    "eval.started": ["evalId"],
    "eval.decided": ["evalId", "decision"],
    "ticket.opened": ["ticket"],
    "ticket.ended": ["ticketId", "outcome", "reason"],
    "ticket.resumed": ["ticketId"],
    "subscription.added": ["subscription"],
    "subscription.removed": ["ticketId", "threadId"],
    "assignment.created": ["assignment"],
    "assignment.started": ["assignmentId"],
    "assignment.ended": ["assignmentId", "outcome"],
    "input.fanned_out": ["input"],
    "input.delivered": ["inputId"],
    "input.undelivered": ["inputId", "reason"],
    "report.recorded": ["report"],
    "attention.opened": ["attention"],
    "message.queued": ["message"],
    "message.sent": ["messageId"],
    "message.failed": ["messageId", "reason"],
    "source.failed": ["source", "error"],
    "source.recovered": ["source"],
    "policy.changed": ["policy"],
};
export function makeEvent(type, data, at) {
    return { type, data, at, seq: 0 };
}
export function validateEvent(event) {
    if (!(event.type in REQUIRED_KEYS))
        throw new Error(`unknown event type: ${event.type}`);
    for (const key of REQUIRED_KEYS[event.type]) {
        if (!(key in event.data))
            throw new Error(`${event.type} missing payload: ${key}`);
    }
}
//# sourceMappingURL=events.js.map