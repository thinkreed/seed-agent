/**
 * 上下文组织：Inline & Spill。
 *
 * 原则：窗口当 Cache 用 —— 热的 Inline 进上下文，冷的只留 ID（Spill），
 * 模型按需经 recall 工具逐跳展开（链式召回）。
 */

import type { State } from "./domain.ts";
import { ticketReport } from "./domain.ts";
import { stageOf } from "./fsm.ts";
import type { AssessContext } from "./ports.ts";

export interface ContextBudget {
  /** 单个对象最多内联多少字符（超过即 Spill）。 */
  readonly spillChars: number;
  /** 单次召回最多返回多少字符。 */
  readonly inlineChars: number;
  /** 一批最多内联多少条 Trigger。 */
  readonly maxTriggers: number;
  /** 最多内联多少张工单。 */
  readonly maxTickets: number;
}

export const DEFAULT_BUDGET: ContextBudget = {
  spillChars: 200,
  inlineChars: 2000,
  maxTriggers: 12,
  maxTickets: 6,
};

export interface Handle {
  readonly kind: "trigger" | "thread" | "ticket";
  readonly id: string;
}

export interface InlineText {
  readonly text: string;
  readonly truncated: boolean;
  readonly chars: number;
}

export interface TriggerView {
  readonly id: string;
  readonly source: string;
  readonly actor: string;
  readonly at: number;
  readonly threadIds: readonly string[];
  readonly channelIds: readonly string[];
  readonly text: InlineText;
}

export interface TicketView {
  readonly id: string;
  readonly shortName: string;
  readonly state: string;
  readonly stage?: string;
  readonly scope: string;
  readonly strength: string;
  readonly report?: { readonly status: string; readonly summary: InlineText };
}

export interface AssessmentView {
  readonly threadId: string;
  readonly policyVersion: string | null;
  readonly triggers: readonly TriggerView[];
  readonly tickets: readonly TicketView[];
  readonly handles: readonly Handle[];
  readonly spilled: readonly Handle[];
}

export function clip(text: string, limit: number): InlineText {
  const normalized = text.replaceAll("\r\n", "\n");
  if (normalized.length <= limit) {
    return { text: normalized, truncated: false, chars: normalized.length };
  }
  return { text: `${normalized.slice(0, limit)}…`, truncated: true, chars: normalized.length };
}

/** 由评估上下文（端口）直接构造视图：真实 LLM 评估器用这个入口。 */
export function buildView(context: AssessContext, budget: ContextBudget = DEFAULT_BUDGET): AssessmentView {
  const batchIds = new Set(context.triggers.map((trigger) => trigger.id));
  const history = (context.history ?? []).filter((trigger) => !batchIds.has(trigger.id));
  const triggers = [...history, ...context.triggers].sort(
    (a, b) => a.at - b.at || a.id.localeCompare(b.id),
  );
  const inlineTriggers = triggers.slice(-budget.maxTriggers);
  const spilledIds = triggers.slice(0, Math.max(0, triggers.length - budget.maxTriggers));
  const tickets = [...context.tickets].sort((a, b) => a.id.localeCompare(b.id)).slice(0, budget.maxTickets);

  const triggerViews: TriggerView[] = inlineTriggers.map((trigger) => ({
    id: trigger.id,
    source: trigger.source,
    actor: trigger.actor,
    at: trigger.at,
    threadIds: trigger.threadIds,
    channelIds: trigger.channelIds,
    text: clip(trigger.text, budget.spillChars),
  }));

  const ticketViews: TicketView[] = tickets.map((ticket) => ({
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
      ...inlineTriggers.map((trigger) => ({ kind: "trigger" as const, id: trigger.id })),
      ...tickets.map((ticket) => ({ kind: "ticket" as const, id: ticket.id })),
    ],
    spilled: spilledIds.map((trigger) => ({ kind: "trigger" as const, id: trigger.id })),
  };
}

/** 把一批 Trigger + 线程上的工单组织成 Assessment 的可读视图。纯函数，确定性输出。 */
export function buildAssessmentView(
  state: State,
  threadId: string,
  budget: ContextBudget = DEFAULT_BUDGET,
): AssessmentView {
  const triggers = Object.values(state.triggers)
    .filter((trigger) => trigger.threadIds.includes(threadId))
    .sort((a, b) => a.at - b.at || a.id.localeCompare(b.id));

  const inlineTriggers = triggers.slice(-budget.maxTriggers);
  const spilledIds = triggers.slice(0, Math.max(0, triggers.length - budget.maxTriggers));

  const triggerViews: TriggerView[] = inlineTriggers.map((trigger) => ({
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

  const ticketViews: TicketView[] = tickets.map((ticket) => {
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

  const handles: Handle[] = [
    { kind: "thread" as const, id: threadId },
    ...inlineTriggers.map((trigger) => ({ kind: "trigger" as const, id: trigger.id })),
    ...tickets.map((ticket) => ({ kind: "ticket" as const, id: ticket.id })),
  ];

  return {
    threadId,
    policyVersion: state.policy?.version ?? null,
    triggers: triggerViews,
    tickets: ticketViews,
    handles,
    spilled: spilledIds.map((trigger) => ({ kind: "trigger" as const, id: trigger.id })),
  };
}