/** 评估执行：把一批 Trigger 交给 Assessment（模型侧），并把 Decision 落成事件。 */

import type { Clock } from "./clock.ts";
import { ev } from "./builders.ts";
import type { Decision, Eval, Mandate, OutboundMessage, Policy, Ticket, Trigger } from "./domain.ts";
import type { Effects } from "./effects.ts";
import type { AnyEvent } from "./events.ts";
import type { IdFactory } from "./ids.ts";
import type { AssessContext, Assessor } from "./ports.ts";
import type { SqliteStore } from "./store.ts";

export interface EvalRunnerOptions {
  readonly store: SqliteStore;
  readonly clock: Clock;
  readonly ids: IdFactory;
  readonly assessor: Assessor;
  /** 回复决策需要把 message.queued 的发送放进 outbox。 */
  readonly effects?: Effects;
}

export class EvalRunner {
  private readonly store: SqliteStore;
  private readonly clock: Clock;
  private readonly ids: IdFactory;
  private readonly assessor: Assessor;
  private readonly effects: Effects | undefined;

  constructor(options: EvalRunnerOptions) {
    this.store = options.store;
    this.clock = options.clock;
    this.ids = options.ids;
    this.assessor = options.assessor;
    this.effects = options.effects;
  }

  async run(evaluation: Eval): Promise<AnyEvent[]> {
    const now = this.clock.now();
    this.store.append(ev.evalStarted(evaluation.id, now));
    const state = this.store.state();
    const context: AssessContext = {
      threadId: evaluation.threadId,
      triggers: evaluation.triggerIds
        .map((id) => state.triggers[id])
        .filter((item): item is Trigger => item !== undefined),
      history: Object.values(state.triggers)
        .filter(
          (item) =>
            item.threadIds.includes(evaluation.threadId) &&
            !evaluation.triggerIds.includes(item.id),
        )
        .sort((a, b) => a.at - b.at || a.id.localeCompare(b.id))
        .slice(-5),
      tickets: Object.values(state.tickets).filter((ticket) =>
        ticket.threadIds.includes(evaluation.threadId),
      ),
      policy: state.policy,
    };
    const decision = await this.assessor.assess(context);
    const produced: AnyEvent[] = [ev.evalDecided(evaluation.id, decision, now)];
    for (const triggerId of evaluation.triggerIds) {
      produced.push(ev.dispositionRecorded(triggerId, "evaluated", now));
    }
    produced.push(...this.apply(evaluation, decision, now));
    return this.store.appendAll(produced);
  }

  private apply(evaluation: Eval, decision: Decision, now: number): AnyEvent[] {
    const state = this.store.state();
    if (decision.kind === "reply") {
      const triggers = evaluation.triggerIds
        .map((id) => state.triggers[id])
        .filter((item): item is Trigger => item !== undefined);
      const address = triggers[0]?.channelIds[0];
      const text = decision.reply?.trim();
      if (!address || !text) return [];
      const message: OutboundMessage = {
        id: this.ids.next("msg"),
        ticketId: "",
        channelId: address,
        address,
        text: text.slice(0, 2000),
        at: now,
      };
      this.effects?.enqueue(this.ids.next("eff"), "send", { messageId: message.id }, now);
      return [ev.messageQueued(message, now)];
    }
    if (decision.kind === "accept" && state.policy && state.policy.acceptMode !== "record") {
      return this.openTicket(evaluation, decision, state.policy, now);
    }
    if (decision.kind === "stop") {
      return Object.values(state.tickets)
        .filter((ticket) => ticket.state === "open" && ticket.threadIds.includes(evaluation.threadId))
        .map((ticket) => ev.ticketEnded(ticket.id, "stopped", decision.reason || "eval-stop", now));
    }
    return [];
  }

  private openTicket(
    evaluation: Eval,
    decision: Decision,
    policy: Policy,
    now: number,
  ): AnyEvent[] {
    const state = this.store.state();
    const triggers = evaluation.triggerIds
      .map((id) => state.triggers[id])
      .filter((item): item is Trigger => item !== undefined);
    const first = triggers[0];
    const mandate: Mandate = decision.mandate ?? {
      policyVersion: policy.version,
      strength: decision.strength,
      scope: decision.scope,
      source: first?.source ?? "",
      actor: first?.actor ?? "",
      rules: decision.rules,
      triggerId: evaluation.triggerIds[0] ?? "",
    };
    // Correlation：一条 Trigger 可同时属于多个 Thread（如 IM 话题 + GitHub PR），
    // 工单订阅全部 Thread，之后任一线程的后续事件都直通同一个 Worker（文章 §1 连续）。
    const related = [...new Set(triggers.flatMap((item) => item.threadIds))];
    const threadIds = [
      evaluation.threadId,
      ...related.filter((threadId) => threadId !== evaluation.threadId),
    ];
    const ticket: Ticket = {
      id: this.ids.next("tk"),
      shortName: this.ids.next("t"),
      mandate,
      threadIds,
      channelIds: [...new Set(triggers.flatMap((item) => item.channelIds))],
      state: "open",
      stopped: false,
      createdAt: now,
    };
    return [
      ev.ticketOpened(ticket, now),
      ...threadIds.map((threadId, index) =>
        ev.subscriptionAdded(
          { ticketId: ticket.id, threadId, kind: index === 0 ? "own" : "context" },
          now,
        ),
      ),
    ];
  }
}