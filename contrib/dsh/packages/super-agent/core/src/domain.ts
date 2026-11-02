/**
 * 领域模型：纯数据，无 IO、无副作用。
 * 概念与不变量对齐 dsh-superagent-prototype/docs/001-domain.md。
 */
export type DecisionKind = "accept" | "stop" | "ignore" | "unavailable" | "reply";
export type Strength = "explicit" | "inferred";
export type TicketState = "open" | "ended";
export type AssignmentState = "pending" | "running" | "ended";
export type ReportStatus = "progress" | "waiting" | "ready" | "blocked" | "failed" | "dropped";
export type SubscriptionKind = "own" | "context";
export type EvalState = "queued" | "running" | "decided" | "unavailable";
export type Disposition = "filtered" | "queued" | "evaluated" | "fanned_out";
export type AcceptMode = "auto" | "record" | "off";
/** 工单阶段：派生值，绝不落库。 */
export type Stage =
  | "person/delivery"
  | "person/answer"
  | "person/review"
  | "person/blocked"
  | "person/failed"
  | "working/queued"
  | "idle"
  | "working";

export interface Trigger {
  readonly id: string;
  readonly source: string;
  readonly actor: string;
  readonly text: string;
  readonly threadIds: readonly string[];
  readonly channelIds: readonly string[];
  readonly at: number;
}

export interface Thread {
  readonly id: string;
  readonly source: string;
  readonly at: number;
}

export interface Channel {
  readonly id: string;
  readonly threadId: string;
  readonly address: string;
}

/** 确定性准入规则（Gate 用）。 */
export interface PolicyRule {
  readonly source: string;
  readonly actor: string;
  readonly allow: boolean;
  readonly strength: Strength;
  readonly note: string;
}

export interface Policy {
  readonly version: string;
  readonly rules: readonly PolicyRule[];
  readonly acceptMode: AcceptMode;
  readonly allowedSenders: readonly (readonly [string, string])[];
  /** 这些 Source 必须显式 @ 才准入（程序层 Fast Path，文章 §3.1）。 */
  readonly mentionRequiredFor?: readonly string[];
  /** 识别"显式请求"的提及词。 */
  readonly mentionTokens?: readonly string[];
}
/** 受理所授予的权力。不可变。 */
export interface Mandate {
  readonly policyVersion: string;
  readonly strength: Strength;
  readonly scope: string;
  readonly source: string;
  readonly actor: string;
  readonly rules: readonly string[];
  readonly triggerId: string;
}
export interface Decision {
  readonly kind: DecisionKind;
  readonly strength: Strength;
  readonly reason: string;
  readonly rules: readonly string[];
  readonly scope: string;
  /** kind=reply 时由 Router 直接对人说的话（不建工单）。 */
  readonly reply?: string;
  readonly mandate?: Mandate;
}
export interface Ticket {
  readonly id: string;
  readonly shortName: string;
  readonly mandate: Mandate;
  readonly threadIds: readonly string[];
  readonly channelIds: readonly string[];
  readonly state: TicketState;
  readonly stopped: boolean;
  readonly createdAt: number;
}

export interface Assignment {
  readonly id: string;
  readonly ticketId: string;
  readonly state: AssignmentState;
  readonly executorRef: string;
  readonly createdAt: number;
}

export interface Subscription {
  readonly ticketId: string;
  readonly threadId: string;
  readonly kind: SubscriptionKind;
}

export interface Report {
  readonly ticketId: string;
  readonly assignmentId: string;
  readonly status: ReportStatus;
  readonly summary: string;
  readonly at: number;
}

export interface Input {
  readonly id: string;
  readonly ticketId: string;
  readonly kind: string;
  readonly ref: string;
  readonly at: number;
}

export interface Attention {
  readonly id: string;
  readonly ticketId: string;
  readonly question: string;
  readonly at: number;
}

/** 对外消息（回复/通知）：先入账，再由 effects 真正发送。 */
export interface OutboundMessage {
  readonly id: string;
  readonly ticketId: string;
  readonly channelId: string;
  readonly address: string;
  readonly text: string;
  readonly at: number;
}

export interface Eval {
  readonly id: string;
  readonly threadId: string;
  readonly triggerIds: readonly string[];
  readonly state: EvalState;
  readonly at: number;
}

/** reducer 的只读快照。 */
export interface State {
  triggers: Readonly<Record<string, Trigger>>;
  threads: Readonly<Record<string, Thread>>;
  tickets: Readonly<Record<string, Ticket>>;
  evals: Readonly<Record<string, Eval>>;
  assignments: Readonly<Record<string, Assignment>>;
  subscriptions: readonly Subscription[];
  reports: Readonly<Record<string, readonly Report[]>>;
  inputs: Readonly<Record<string, Input>>;
  attentions: Readonly<Record<string, Attention>>;
  messages: Readonly<Record<string, OutboundMessage>>;
  sentMessages: ReadonlySet<string>;
  messageErrors: Readonly<Record<string, string>>;
  dispositions: Readonly<Record<string, Disposition>>;
  undelivered: ReadonlySet<string>;
  delivered: ReadonlySet<string>;
  /** Source 最近一次失败（Watchdog 的基础设施判据）。 */
  sourceFailures: Readonly<Record<string, string>>;
  policy: Policy | null;
}

export function emptyState(): State {
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
    sentMessages: new Set<string>(),
    messageErrors: {},
    dispositions: {},
    undelivered: new Set<string>(),
    delivered: new Set<string>(),
    sourceFailures: {},
    policy: null,
  };
}

export function ticketReport(state: State, ticketId: string): Report | undefined {
  const history = state.reports[ticketId];
  return history && history.length > 0 ? history[history.length - 1] : undefined;
}

export function subscribedTickets(state: State, threadId: string): string[] {
  return state.subscriptions.filter((item) => item.threadId === threadId).map((item) => item.ticketId);
}

export function openAssignment(state: State, ticketId: string): Assignment | undefined {
  return Object.values(state.assignments).find(
    (item) => item.ticketId === ticketId && item.state !== "ended",
  );
}