/** 评估执行：把一批 Trigger 交给 Assessment（模型侧），并把 Decision 落成事件。 */

import type { Clock } from "./clock.ts";
import { ev } from "./builders.ts";
import type { Decision, Eval, Mandate, Policy, Ticket, Trigger } from "./domain.ts";
import type { AnyEvent } from "./events.ts";
import type { IdFactory } from "./ids.ts";
import type { AssessContext, Assessor } from "./ports.ts";
import type { SqliteStore } from "./store.ts";

export interface EvalRunnerOptions {
  readonly store: SqliteStore;
  readonly clock: Clock;
  readonly ids: IdFactory;
  readonly assessor: Assessor;
}

export class EvalRunner {
  private readonly store: SqliteStore;
  private readonly clock: Clock;
  private readonly ids: IdFactory;
  private readonly assessor: Assessor;

  constructor(options: EvalRunnerOptions) {
    this.store = options.store;
    this.clock = options.clock;
    this.ids = options.ids;
    this.assessor = options.assessor;
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
    const ticket: Ticket = {
      id: this.ids.next("tk"),
      shortName: this.ids.next("t"),
      mandate,
      threadIds: [evaluation.threadId],
      channelIds: [...new Set(triggers.flatMap((item) => item.channelIds))],
      state: "open",
      stopped: false,
      createdAt: now,
    };
    return [
      ev.ticketOpened(ticket, now),
      ev.subscriptionAdded({ ticketId: ticket.id, threadId: evaluation.threadId, kind: "own" }, now),
    ];
  }
}