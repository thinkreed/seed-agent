/** reducer：唯一纯状态推导。无 IO、无时钟、无随机。 */

import type { State } from "./domain.ts";
import { emptyState } from "./domain.ts";
import type { AnyEvent } from "./events.ts";

export class UnknownEventError extends Error {
  constructor(type: string) {
    super(`unknown event: ${type}`);
    this.name = "UnknownEventError";
  }
}

export class InvalidTransitionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidTransitionError";
  }
}

function patch(state: State, changes: Partial<State>): State {
  return { ...state, ...changes };
}

export function apply(state: State, event: AnyEvent): State {
  switch (event.type) {
    case "trigger.recorded": {
      const trigger = event.data.trigger;
      return patch(state, { triggers: { ...state.triggers, [trigger.id]: trigger } });
    }
    case "thread.declared": {
      const thread = event.data.thread;
      return patch(state, { threads: { ...state.threads, [thread.id]: thread } });
    }
    case "trigger.filtered": {
      return patch(state, {
        dispositions: { ...state.dispositions, [event.data.triggerId]: "filtered" },
      });
    }
    case "disposition.recorded": {
      return patch(state, {
        dispositions: {
          ...state.dispositions,
          [event.data.triggerId]: event.data.disposition,
        },
      });
    }
    case "eval.queued": {
      const evaluation = event.data.eval;
      return patch(state, { evals: { ...state.evals, [evaluation.id]: evaluation } });
    }
    case "eval.started": {
      const evaluation = state.evals[event.data.evalId];
      if (!evaluation) throw new InvalidTransitionError(`unknown eval ${event.data.evalId}`);
      if (evaluation.state !== "queued") {
        throw new InvalidTransitionError(`eval ${evaluation.id}: ${evaluation.state} -> running`);
      }
      return patch(state, {
        evals: { ...state.evals, [evaluation.id]: { ...evaluation, state: "running" } },
      });
    }
    case "eval.decided": {
      const evaluation = state.evals[event.data.evalId];
      if (!evaluation) throw new InvalidTransitionError(`unknown eval ${event.data.evalId}`);
      if (evaluation.state !== "queued" && evaluation.state !== "running") {
        throw new InvalidTransitionError(`eval ${evaluation.id}: ${evaluation.state} -> decided`);
      }
      return patch(state, {
        evals: { ...state.evals, [evaluation.id]: { ...evaluation, state: "decided" } },
      });
    }
    case "ticket.opened": {
      const ticket = event.data.ticket;
      if (state.tickets[ticket.id]) throw new InvalidTransitionError(`ticket ${ticket.id} opened twice`);
      return patch(state, { tickets: { ...state.tickets, [ticket.id]: ticket } });
    }
    case "ticket.ended": {
      const ticket = state.tickets[event.data.ticketId];
      if (!ticket) throw new InvalidTransitionError(`unknown ticket ${event.data.ticketId}`);
      if (ticket.state === "ended") throw new InvalidTransitionError(`ticket ${ticket.id} ended twice`);
      const stopped = ticket.stopped || event.data.outcome === "stopped";
      return patch(state, {
        tickets: { ...state.tickets, [ticket.id]: { ...ticket, state: "ended", stopped } },
      });
    }
    case "ticket.resumed": {
      const ticket = state.tickets[event.data.ticketId];
      if (!ticket) throw new InvalidTransitionError(`unknown ticket ${event.data.ticketId}`);
      if (ticket.stopped) throw new InvalidTransitionError(`ticket ${ticket.id} was stopped by a person`);
      return patch(state, { tickets: { ...state.tickets, [ticket.id]: { ...ticket, state: "open" } } });
    }
    case "subscription.added": {
      const subscription = event.data.subscription;
      const exists = state.subscriptions.some(
        (item) => item.ticketId === subscription.ticketId && item.threadId === subscription.threadId,
      );
      if (exists) return state;
      return patch(state, { subscriptions: [...state.subscriptions, subscription] });
    }
    case "subscription.removed": {
      const { ticketId, threadId } = event.data;
      return patch(state, {
        subscriptions: state.subscriptions.filter(
          (item) => !(item.ticketId === ticketId && item.threadId === threadId),
        ),
      });
    }
    case "assignment.created": {
      const assignment = event.data.assignment;
      if (state.assignments[assignment.id]) {
        throw new InvalidTransitionError(`assignment ${assignment.id} created twice`);
      }
      return patch(state, { assignments: { ...state.assignments, [assignment.id]: assignment } });
    }
    case "assignment.started": {
      const assignment = state.assignments[event.data.assignmentId];
      if (!assignment) throw new InvalidTransitionError(`unknown assignment ${event.data.assignmentId}`);
      if (assignment.state !== "pending") {
        throw new InvalidTransitionError(`assignment ${assignment.id}: ${assignment.state} -> running`);
      }
      return patch(state, {
        assignments: { ...state.assignments, [assignment.id]: { ...assignment, state: "running" } },
      });
    }
    case "assignment.ended": {
      const assignment = state.assignments[event.data.assignmentId];
      if (!assignment) throw new InvalidTransitionError(`unknown assignment ${event.data.assignmentId}`);
      if (assignment.state === "ended") {
        throw new InvalidTransitionError(`assignment ${assignment.id} ended twice`);
      }
      return patch(state, {
        assignments: { ...state.assignments, [assignment.id]: { ...assignment, state: "ended" } },
      });
    }
    case "input.fanned_out": {
      const input = event.data.input;
      if (state.inputs[input.id]) return state;
      return patch(state, { inputs: { ...state.inputs, [input.id]: input } });
    }
    case "input.delivered": {
      const undelivered = new Set(state.undelivered);
      undelivered.delete(event.data.inputId);
      const delivered = new Set(state.delivered);
      delivered.add(event.data.inputId);
      return patch(state, { undelivered, delivered });
    }
    case "input.undelivered": {
      const undelivered = new Set(state.undelivered);
      undelivered.add(event.data.inputId);
      const delivered = new Set(state.delivered);
      delivered.delete(event.data.inputId);
      return patch(state, { undelivered, delivered });
    }
    case "report.recorded": {
      const report = event.data.report;
      if (!state.tickets[report.ticketId]) {
        throw new InvalidTransitionError(`report for unknown ticket ${report.ticketId}`);
      }
      const history = state.reports[report.ticketId] ?? [];
      return patch(state, { reports: { ...state.reports, [report.ticketId]: [...history, report] } });
    }
    case "attention.opened": {
      const attention = event.data.attention;
      return patch(state, { attentions: { ...state.attentions, [attention.ticketId]: attention } });
    }
    case "message.queued": {
      const message = event.data.message;
      if (state.messages[message.id]) return state;
      return patch(state, { messages: { ...state.messages, [message.id]: message } });
    }
    case "message.sent": {
      const sentMessages = new Set(state.sentMessages);
      sentMessages.add(event.data.messageId);
      return patch(state, { sentMessages });
    }
    case "message.failed": {
      return patch(state, {
        messageErrors: { ...state.messageErrors, [event.data.messageId]: event.data.reason },
      });
    }
    case "source.failed": {
      return patch(state, {
        sourceFailures: { ...state.sourceFailures, [event.data.source]: event.data.error },
      });
    }
    case "source.recovered": {
      const sourceFailures = { ...state.sourceFailures };
      delete sourceFailures[event.data.source];
      return patch(state, { sourceFailures });
    }
    case "policy.changed": {
      return patch(state, { policy: event.data.policy });
    }
    default: {
      const unknown = event as { type: string };
      throw new UnknownEventError(unknown.type);
    }
  }
}

export function rebuild(events: readonly AnyEvent[], initial: State = emptyState()): State {
  let state = initial;
  for (const event of events) state = apply(state, event);
  return state;
}