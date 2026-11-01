/** 引擎：唯一的状态机驱动者。 */

import type { Clock } from "./clock.ts";
import { Actions } from "./actions.ts";
import { ev } from "./builders.ts";
import type { Eval, Input, Policy, Report, State, Trigger } from "./domain.ts";
import { subscribedTickets } from "./domain.ts";
import { Effects } from "./effects.ts";
import { EvalRunner } from "./eval_runner.ts";
import type { AnyEvent } from "./events.ts";
import type { IdFactory } from "./ids.ts";
import { gate } from "./policy.ts";
import type { Assessor, ChannelWriter, Executor } from "./ports.ts";
import { Router } from "./router.ts";
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
  private readonly router: Router;
  private paused = false;

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
      ...(this.channels ? { channels: this.channels } : {}),
    });
    this.effects = new Effects(this.store, this.clock, {
      launch: (item) => this.actions.launch(item.payload.assignmentId as string),
      deliver: (item) => this.actions.deliver(item.payload.inputId as string),
      send: (item) => this.actions.send(item.payload.messageId as string),
    });
    this.router = new Router({ store: this.store, clock: this.clock, effects: this.effects });
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
    if (this.paused) return [];
    const produced: AnyEvent[] = [];
    for (;;) {
      // 同一轮内所有 Thread 的 queued Eval 并发交给评估器：Router 可把它们合并成一次 LLM 调用（批处理）。
      const queued = Object.values(this.state.evals).filter((item) => item.state === "queued");
      if (queued.length === 0) break;
      const batches = await Promise.all(queued.map((evaluation) => this.evalRunner.run(evaluation)));
      for (const batch of batches) produced.push(...batch);
    }
    produced.push(...this.actions.dispatch(this.slots, this.effects));
    // 有渠道时才产出对外回复；没有 ChannelWriter 的纯内核算例保持原行为。
    if (this.channels) produced.push(...this.router.queueReplies());
    const { produced: effectEvents } = await this.effects.drain();
    produced.push(...this.append(effectEvents));
    return produced;
  }

  // ---------- 输入 ----------

  personMessage(ticketId: string, text: string): AnyEvent[] {
    return this.actions.personMessage(ticketId, text, this.effects);
  }

  /** Watchdog/运维：暂停处理（Source 仍可继续记录事件）。 */
  pause(): void {
    this.paused = true;
  }

  resume(): void {
    this.paused = false;
  }

  get isPaused(): boolean {
    return this.paused;
  }

  /** 重试：结束当前 assignment 并投递一条 retry 输入，让工单重新排到执行器。 */
  retry(ticketId: string): AnyEvent[] {
    return this.actions.retry(ticketId, this.effects);
  }

  /** Worker 取消订阅：之后同一 Thread 的事件不再直通该工单（回到 Router 评估）。 */
  unsubscribe(ticketId: string, threadId?: string): AnyEvent[] {
    const now = this.clock.now();
    const removed = this.state.subscriptions.filter(
      (item) => item.ticketId === ticketId && (threadId === undefined || item.threadId === threadId),
    );
    return this.append(removed.map((item) => ev.subscriptionRemoved(ticketId, item.threadId, now)));
  }

  /**
   * Worker 交回 Router：取消该工单的订阅，并把 Thread 上最新事件重新入评估队列，
   * 由 Router 决定新建工单、忽略或另作处理（文章 §3.2 的 hand back）。
   */
  handback(ticketId: string, _reason = ''): AnyEvent[] {
    const now = this.clock.now();
    const state = this.state;
    const ticket = state.tickets[ticketId];
    if (!ticket) throw new Error(`unknown ticket ${ticketId}`);
    const threadIds = state.subscriptions
      .filter((item) => item.ticketId === ticketId)
      .map((item) => item.threadId);
    const produced: AnyEvent[] = threadIds.map((threadId) =>
      ev.subscriptionRemoved(ticketId, threadId, now));
    for (const threadId of threadIds) {
      const latest = Object.values(state.triggers)
        .filter((trigger) => trigger.threadIds.includes(threadId))
        .sort((a, b) => a.at - b.at || a.id.localeCompare(b.id))
        .at(-1);
      if (!latest) continue;
      const queued = Object.values(state.evals).find(
        (item) => item.threadId === threadId && item.state === "queued",
      );
      const triggerIds = queued ? [...queued.triggerIds, latest.id] : [latest.id];
      produced.push(ev.dispositionRecorded(latest.id, "queued", now));
      produced.push(ev.evalQueued({
        id: queued?.id ?? this.ids.next("eval"),
        threadId,
        triggerIds,
        state: "queued",
        at: now,
      }, now));
    }
    return this.append(produced);
  }

  /** 进程重启后：把 running 的 assignment 收口，并给执行器留下恢复注记。 */
  recoverAfterRestart(): AnyEvent[] {
    return this.actions.recoverAfterRestart(this.effects);
  }

  report(report: Report): AnyEvent[] {
    return this.actions.report(report);
  }

  private append(events: readonly AnyEvent[]): AnyEvent[] {
    return events.length > 0 ? this.store.appendAll(events) : [];
  }
}