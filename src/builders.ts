/** 事件构造器：集中一处，引擎只调用这里。 */

import type {
  Assignment,
  Attention,
  Decision,
  Disposition,
  Eval,
  Input,
  Policy,
  Report,
  Subscription,
  Ticket,
  Thread,
  Trigger,
} from "./domain.ts";
import type { AnyEvent } from "./events.ts";
import { makeEvent } from "./events.ts";

export const ev = {
  triggerRecorded: (trigger: Trigger, at: number): AnyEvent =>
    makeEvent("trigger.recorded", { trigger }, at),
  threadDeclared: (thread: Thread, at: number): AnyEvent =>
    makeEvent("thread.declared", { thread }, at),
  triggerFiltered: (triggerId: string, layer: string, reason: string, at: number): AnyEvent =>
    makeEvent("trigger.filtered", { triggerId, layer, reason }, at),
  dispositionRecorded: (triggerId: string, disposition: Disposition, at: number): AnyEvent =>
    makeEvent("disposition.recorded", { triggerId, disposition }, at),
  evalQueued: (evaluation: Eval, at: number): AnyEvent =>
    makeEvent("eval.queued", { eval: evaluation }, at),
  evalStarted: (evalId: string, at: number): AnyEvent =>
    makeEvent("eval.started", { evalId }, at),
  evalDecided: (evalId: string, decision: Decision, at: number): AnyEvent =>
    makeEvent("eval.decided", { evalId, decision }, at),
  ticketOpened: (ticket: Ticket, at: number): AnyEvent =>
    makeEvent("ticket.opened", { ticket }, at),
  ticketEnded: (ticketId: string, outcome: string, reason: string, at: number): AnyEvent =>
    makeEvent("ticket.ended", { ticketId, outcome, reason }, at),
  ticketResumed: (ticketId: string, at: number): AnyEvent =>
    makeEvent("ticket.resumed", { ticketId }, at),
  subscriptionAdded: (subscription: Subscription, at: number): AnyEvent =>
    makeEvent("subscription.added", { subscription }, at),
  subscriptionRemoved: (ticketId: string, threadId: string, at: number): AnyEvent =>
    makeEvent("subscription.removed", { ticketId, threadId }, at),
  assignmentCreated: (assignment: Assignment, at: number): AnyEvent =>
    makeEvent("assignment.created", { assignment }, at),
  assignmentStarted: (assignmentId: string, at: number): AnyEvent =>
    makeEvent("assignment.started", { assignmentId }, at),
  assignmentEnded: (assignmentId: string, outcome: string, at: number): AnyEvent =>
    makeEvent("assignment.ended", { assignmentId, outcome }, at),
  inputFannedOut: (input: Input, at: number): AnyEvent =>
    makeEvent("input.fanned_out", { input }, at),
  inputDelivered: (inputId: string, at: number): AnyEvent =>
    makeEvent("input.delivered", { inputId }, at),
  inputUndelivered: (inputId: string, reason: string, at: number): AnyEvent =>
    makeEvent("input.undelivered", { inputId, reason }, at),
  reportRecorded: (report: Report, at: number): AnyEvent =>
    makeEvent("report.recorded", { report }, at),
  attentionOpened: (attention: Attention, at: number): AnyEvent =>
    makeEvent("attention.opened", { attention }, at),
  policyChanged: (policy: Policy, at: number): AnyEvent =>
    makeEvent("policy.changed", { policy }, at),
};