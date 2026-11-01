/** 引擎：唯一的状态机驱动者。 */

import type { Clock } from "./clock.ts";
import { Actions } from "./actions.ts";
import { ev } from "./builders.ts";
import type { Eval, Input, Policy, Report, State, Ticket, Trigger } from "./domain.ts";
import { subscribedTickets } from "./domain.ts";
import { Effects } from "./effects.ts";
import { EvalRunner } from "./eval_runner.ts";
import type { AnyEvent } from "./events.ts";
import type { IdFactory } from "./ids.ts";
import { gate } from "./policy.ts";
import type { Assessor, ChannelWriter, Executor } from "./ports.ts";
import type { SqliteStore } from "./store.ts";

export interface EngineOptions {
  store: SqliteStore;
  clock: Clock;
  ids: IdFactory;
  assessor: Assessor;
  executor: Executor;
  channels?: ChannelWriter;
  policy?: Policy | null;
  slots?: number;
}

export class Engine {
  readonly store: SqliteStore;
  readonly clock: Clock;
  readonly ids: IdFactory;
  readonly assessor: Assessor;
  readonly executor: Executor;
  readonly slots: number;
  readonly effects: Effects;
  readonly channels: ChannelWriter | undefined;
  private readonly evalRunner: EvalRunner;
  private readonly actions: Actions;

  constructor(options: EngineOptions) {
    this.store = options.store;
    this.clock = options.clock;
    this.ids = options.ids;
    this.assessor = options.assessor;
    this.executor = options.executor;
    this.slots = options.slots ?? 4;
    this.channels = options.channels;
    this.evalRunner = new EvalRunner({
      store: this.store,
      clock: this.clock,
      ids: this.ids,
      assessor: this.assessor,
    });
    this.actions = new Actions({
      store: this.store,
      clock: this.clock,
      ids: this.ids,
      executor: this.executor,
      channels: this.channels,
    });
    this.effects = new Effects(this.store, this.clock, {
      launch: (item) => this.actions.launch(item.payload.assignmentId as string),
      deliver: (item) => this.actions.deliver(item.payload.inputId as string),
      send: (item) => this.actions.send(item.payload.messageId as string),
    });
    if (options.policy) this.append([ev.policyChanged(options.policy, this.clock.now())]);
  }

  get state(): State {
    return this.store.state();
  }

  // ---------- 摄入 ----------

  ingest(trigger: Trigger): AnyEvent[] {
    const now = this.clock.now();
    const state = this.state;
    if (state.triggers[trigger.id]) return [];

    const threadIds = trigger.threadIds.length > 0 ? trigger.threadIds : [`${trigger.source}:default`];
    const normalized: Trigger = { ...trigger, threadIds, at: trigger.at || now };
    const produced: AnyEvent[] = [ev.triggerRecorded(normalized, now)];

    for (const threadId of threadIds) {
      if (!state.threads[threadId]) {
        produced.push(ev.threadDeclared({ id: threadId, source: trigger.source, at: now }, now));
      }
    }

    const fanOutTo = [...new Set(threadIds.flatMap((threadId) => subscribedTickets(state, threadId)))];
    if (fanOutTo.length > 0) return this.fanOut(normalized, fanOutTo, produced, now);

    const gateResult = gate(state.policy, normalized);
    if (!gateResult.allowed) {
      produced.push(ev.triggerFiltered(normalized.id, "fast", gateResult.reason, now));
      produced.push(ev.dispositionRecorded(normalized.id, "filtered", now));
      return this.append(produced);
    }
    return this.queueEval(normalized, threadIds[0] as string, produced, now);
  }

  private fanOut(
    trigger: Trigger,
    ticketIds: readonly string[],
    produced: AnyEvent[],
    now: number,
  ): AnyEvent[] {
    for (const ticketId of ticketIds) {
      const input: Input = {
        id: this.ids.next("inp"),
        ticketId,
        kind: "trigger",
        ref: trigger.id,
        at: now,
      };
      produced.push(ev.inputFannedOut(input, now));
      this.effects.enqueue(this.ids.next("eff"), "deliver", { inputId: input.id }, now);
    }
    produced.push(ev.dispositionRecorded(trigger.id, "fanned_out", now));
    return this.append(produced);
  }

  private queueEval(
    trigger: Trigger,
    threadId: string,
    produced: AnyEvent[],
    now: number,
  ): AnyEvent[] {
    const queued = Object.values(this.state.evals).find(
      (item) => item.threadId === threadId && item.state === "queued",
    );
    if (queued) {
      // 批处理：上一轮推理期间积压的 Trigger 合并进同一批
      produced.push(ev.evalQueued({ ...queued, triggerIds: [...queued.triggerIds, trigger.id] }, now));
    } else {
      const evaluation: Eval = {
        id: this.ids.next("eval"),
        threadId,
        triggerIds: [...this.queuedTriggerIds(threadId), trigger.id],
        state: "queued",
        at: now,
      };
      produced.push(ev.evalQueued(evaluation, now));
    }
    produced.push(ev.dispositionRecorded(trigger.id, "queued", now));
    return this.append(produced);
  }

  private queuedTriggerIds(threadId: string): string[] {
    const state = this.state;
    return Object.values(state.triggers)
      .filter((item) => item.threadIds.includes(threadId) && state.dispositions[item.id] === "queued")
      .map((item) => item.id)
      .sort();
  }

  // ---------- 驱动 ----------

  async tick(): Promise<AnyEvent[]> {
    const produced: AnyEvent[] = [];
    for (;;) {
      const evaluation = Object.values(this.state.evals).find((item) => item.state === "queued");
      if (!evaluation) break;
      produced.push(...(await this.evalRunner.run(evaluation)));
    }
    produced.push(...this.actions.dispatch(this.slots, this.effects));
    const { produced: effectEvents } = await this.effects.drain();
    produced.push(...this.append(effectEvents));
    return produced;
  }

  // ---------- 输入 ----------

  personMessage(ticketId: string, text: string): AnyEvent[] {
    return this.actions.personMessage(ticketId, text, this.effects);
  }

  report(report: Report): AnyEvent[] {
    return this.actions.report(report);
  }

  private append(events: readonly AnyEvent[]): AnyEvent[] {
    return events.length > 0 ? this.store.appendAll(events) : [];
  }
}