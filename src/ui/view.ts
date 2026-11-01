/** 界面视图模型：把只读 State 投影成桌面端需要的 DTO（纯函数，便于测试）。 */

import type { OutboundMessage, Report, State, Ticket, Trigger } from "../domain.ts";
import { ticketReport } from "../domain.ts";
import { requiresPerson, stageOf } from "../fsm.ts";

export interface UiTicket {
  readonly id: string;
  readonly shortName: string;
  readonly state: string;
  readonly stage: string;
  readonly waitingPerson: boolean;
  readonly source: string;
  readonly actor: string;
  readonly title: string;
  readonly summary: string;
  readonly updatedAt: number;
}

export interface UiState {
  readonly paused: boolean;
  readonly slots: number;
  readonly lastSeq: number;
  readonly counts: {
    readonly total: number;
    readonly open: number;
    readonly ended: number;
    readonly waitingPerson: number;
  };
  readonly tickets: readonly UiTicket[];
}

export interface TimelineItem {
  readonly kind: "trigger" | "input" | "report" | "message";
  readonly at: number;
  readonly who: string;
  readonly text: string;
  readonly status?: string;
}

export interface UiTicketView {
  readonly ticket: UiTicket;
  readonly mandate: {
    readonly source: string;
    readonly actor: string;
    readonly scope: string;
    readonly strength: string;
    readonly policyVersion: string;
  };
  readonly timeline: readonly TimelineItem[];
}

export function buildUiState(state: State, meta: { paused: boolean; slots: number; lastSeq: number }): UiState {
  const tickets = Object.values(state.tickets).map((ticket) => toUiTicket(state, ticket));
  tickets.sort((a, b) => Number(b.waitingPerson) - Number(a.waitingPerson) || b.updatedAt - a.updatedAt || a.id.localeCompare(b.id));
  return {
    paused: meta.paused,
    slots: meta.slots,
    lastSeq: meta.lastSeq,
    counts: {
      total: tickets.length,
      open: tickets.filter((ticket) => ticket.state === "open").length,
      ended: tickets.filter((ticket) => ticket.state === "ended").length,
      waitingPerson: tickets.filter((ticket) => ticket.waitingPerson).length,
    },
    tickets,
  };
}

export function buildTicketView(state: State, ticketId: string): UiTicketView | null {
  const ticket = state.tickets[ticketId];
  if (!ticket) return null;
  const items: TimelineItem[] = [];
  const origin = state.triggers[ticket.mandate.triggerId];
  if (origin) items.push(triggerItem(origin));
  for (const input of Object.values(state.inputs)) {
    if (input.ticketId !== ticketId) continue;
    if (input.kind === "trigger") continue; // 原始触发已作为 trigger 展示
    items.push({
      kind: "input",
      at: input.at,
      who: input.kind === "resume" ? "system" : "operator",
      text: input.ref,
      status: input.kind,
    });
  }
  for (const report of state.reports[ticketId] ?? []) items.push(reportItem(report));
  for (const message of Object.values(state.messages)) {
    if (message.ticketId !== ticketId) continue;
    items.push(messageItem(message));
  }
  items.sort((a, b) => a.at - b.at);
  return {
    ticket: toUiTicket(state, ticket),
    mandate: {
      source: ticket.mandate.source,
      actor: ticket.mandate.actor,
      scope: ticket.mandate.scope,
      strength: ticket.mandate.strength,
      policyVersion: ticket.mandate.policyVersion,
    },
    timeline: items,
  };
}

/** 事件流一行：只保留可读摘要，避免把整个 payload 抛给界面。 */
export function eventRow(event: { seq: number; type: string; at: number }): { seq: number; type: string; at: number } {
  return { seq: event.seq, type: event.type, at: event.at };
}

function toUiTicket(state: State, ticket: Ticket): UiTicket {
  const stage = stageOf(state, ticket);
  const report = ticketReport(state, ticket.id);
  const origin = state.triggers[ticket.mandate.triggerId];
  return {
    id: ticket.id,
    shortName: ticket.shortName,
    state: ticket.state,
    stage,
    waitingPerson: requiresPerson(stage),
    source: ticket.mandate.source,
    actor: ticket.mandate.actor,
    title: titleOf(origin?.text ?? report?.summary ?? ticket.shortName),
    summary: report?.summary ?? "",
    updatedAt: lastActivity(state, ticket),
  };
}

/** 最近一次活动时间：用于工单排序（新事件在上）。 */
function lastActivity(state: State, ticket: Ticket): number {
  let at = ticket.createdAt;
  const origin = state.triggers[ticket.mandate.triggerId];
  if (origin) at = Math.max(at, origin.at);
  for (const report of state.reports[ticket.id] ?? []) at = Math.max(at, report.at);
  for (const input of Object.values(state.inputs)) {
    if (input.ticketId === ticket.id) at = Math.max(at, input.at);
  }
  for (const message of Object.values(state.messages)) {
    if (message.ticketId === ticket.id) at = Math.max(at, message.at);
  }
  return at;
}

function titleOf(text: string): string {
  const first = text.split(/\r?\n/)[0]?.trim() ?? "";
  return first.length > 90 ? `${first.slice(0, 90)}…` : first;
}

function triggerItem(trigger: Trigger): TimelineItem {
  return { kind: "trigger", at: trigger.at, who: trigger.actor || trigger.source, text: trigger.text };
}

function reportItem(report: Report): TimelineItem {
  return { kind: "report", at: report.at, who: "worker", text: report.summary, status: report.status };
}

function messageItem(message: OutboundMessage): TimelineItem {
  return { kind: "message", at: message.at, who: "router", text: message.text, status: "sent" };
}