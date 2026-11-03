/**
 * 事件信封与类型表。
 * 新增事件 = 这里加一行类型 + reducer.ts 加一个分支（architecture 测试会校验）。
 */
import type { Assignment, Attention, Decision, Disposition, Eval, Input, OutboundMessage, Policy, Report, Subscription, Ticket, Thread, Trigger } from "./domain.ts";
export interface EventData {
    "trigger.recorded": {
        trigger: Trigger;
    };
    "thread.declared": {
        thread: Thread;
    };
    "trigger.filtered": {
        triggerId: string;
        layer: string;
        reason: string;
    };
    "disposition.recorded": {
        triggerId: string;
        disposition: Disposition;
    };
    "eval.queued": {
        eval: Eval;
    };
    "eval.started": {
        evalId: string;
    };
    "eval.decided": {
        evalId: string;
        decision: Decision;
    };
    "ticket.opened": {
        ticket: Ticket;
    };
    "ticket.ended": {
        ticketId: string;
        outcome: string;
        reason: string;
    };
    "ticket.resumed": {
        ticketId: string;
    };
    "subscription.added": {
        subscription: Subscription;
    };
    "subscription.removed": {
        ticketId: string;
        threadId: string;
    };
    "assignment.created": {
        assignment: Assignment;
    };
    "assignment.started": {
        assignmentId: string;
    };
    "assignment.ended": {
        assignmentId: string;
        outcome: string;
    };
    "input.fanned_out": {
        input: Input;
    };
    "input.delivered": {
        inputId: string;
    };
    "input.undelivered": {
        inputId: string;
        reason: string;
    };
    "report.recorded": {
        report: Report;
    };
    "attention.opened": {
        attention: Attention;
    };
    "message.queued": {
        message: OutboundMessage;
    };
    "message.sent": {
        messageId: string;
    };
    "message.failed": {
        messageId: string;
        reason: string;
    };
    "source.failed": {
        source: string;
        error: string;
    };
    "source.recovered": {
        source: string;
    };
    "policy.changed": {
        policy: Policy;
    };
}
export type EventType = keyof EventData;
/** 判别联合：switch (event.type) 可自动收窄 data 类型。 */
export type AnyEvent = {
    [K in EventType]: {
        type: K;
        data: EventData[K];
        at: number;
        seq: number;
    };
}[EventType];
export declare const EVENT_TYPES: readonly EventType[];
/** 必填载荷字段：入账前校验，防止半成品事件。 */
export declare const REQUIRED_KEYS: Readonly<Record<EventType, readonly string[]>>;
export declare function makeEvent<K extends EventType>(type: K, data: EventData[K], at: number): AnyEvent;
export declare function validateEvent(event: AnyEvent): void;
