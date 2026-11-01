/** 派工与 effects 处理器：把"要做的事"变成事件，副作用经 outbox。 */

import type { Clock } from "./clock.ts";
import { ev } from "./builders.ts";
import type { Assignment, Input, Report, Ticket } from "./domain.ts";
import { openAssignment } from "./domain.ts";
import type { Effects } from "./effects.ts";
import type { AnyEvent } from "./events.ts";
import type { IdFactory } from "./ids.ts";
import type { Executor, ChannelWriter } from "./ports.ts";
import type { SqliteStore } from "./store.ts";

export interface ActionsOptions {
  readonly store: SqliteStore;
  readonly clock: Clock;
  readonly ids: IdFactory;
  readonly executor: Executor;
  readonly channels?: ChannelWriter;
}

export class Actions {
  private readonly store: SqliteStore;
  private readonly clock: Clock;
  private readonly ids: IdFactory;
  private readonly executor: Executor;
  private readonly channels: ChannelWriter | undefined;

  constructor(options: ActionsOptions) {
    this.store = options.store;
    this.clock = options.clock;
    this.ids = options.ids;
    this.executor = options.executor;
    this.channels = options.channels;
  }

  /** 给空闲工单派活：受并发槽限制。只有"从未派过工"或"有新输入未投递"的工单才启动新 Assignment。
   */
  dispatch(slots: number, effects: Effects): AnyEvent[] {
    const now = this.clock.now();
    const state = this.store.state();
    const live = Object.values(state.assignments).filter((item) => item.state !== "ended");
    let capacity = slots - live.length;
    const produced: AnyEvent[] = [];
    for (const ticket of Object.values(state.tickets).sort((a, b) => a.id.localeCompare(b.id))) {
      if (capacity <= 0) break;
      if (ticket.state !== "open" || ticket.stopped) continue;
      if (openAssignment(state, ticket.id)) continue;
      const neverAssigned = !Object.values(state.assignments).some(
        (item) => item.ticketId === ticket.id,
      );
      const pendingInput = Object.values(state.inputs).some(
        (input) => input.ticketId === ticket.id && !state.delivered.has(input.id),
      );
      if (!neverAssigned && !pendingInput) continue;
      const assignment: Assignment = {
        id: this.ids.next("as"),
        ticketId: ticket.id,
        state: "pending",
        executorRef: "",
        createdAt: now,
      };
      produced.push(ev.assignmentCreated(assignment, now));
      effects.enqueue(this.ids.next("eff"), "launch", { assignmentId: assignment.id }, now);
      capacity -= 1;
    }
    return this.store.appendAll(produced);
  }

  /** effects: launch —— 真正启动执行器。 */
  async launch(assignmentId: string): Promise<AnyEvent[]> {
    const state = this.store.state();
    const assignment = state.assignments[assignmentId];
    if (!assignment) throw new Error(`unknown assignment ${assignmentId}`);
    const ticket: Ticket | undefined = state.tickets[assignment.ticketId];
    if (!ticket) throw new Error(`unknown ticket ${assignment.ticketId}`);
    await this.executor.launch(assignment, ticket);
    return [ev.assignmentStarted(assignment.id, this.clock.now())];
  }

  /** effects: deliver —— 把输入投递给执行器。 */
  async deliver(inputId: string): Promise<AnyEvent[]> {
    const state = this.store.state();
    const input = state.inputs[inputId];
    if (!input) throw new Error(`unknown input ${inputId}`);
    const ticket: Ticket | undefined = state.tickets[input.ticketId];
    if (!ticket) throw new Error(`unknown ticket ${input.ticketId}`);
    await this.executor.deliver(ticket, input);
    return [ev.inputDelivered(input.id, this.clock.now())];
  }

  /** effects: send —— 通过信道把消息发出去。 */
  async send(messageId: string): Promise<AnyEvent[]> {
    const message = this.store.state().messages[messageId];
    if (!message) throw new Error(`unknown message ${messageId}`);
    if (!this.channels) throw new Error("no channel writer configured");
    await this.channels.send(
      { id: message.channelId, threadId: "", address: message.address },
      message.text,
    );
    return [ev.messageSent(message.id, this.clock.now())];
  }

  /** 人的消息进入工单：结束的工单会被 resume（被 stop 的除外）。 */
  personMessage(ticketId: string, text: string, effects: Effects): AnyEvent[] {
    const now = this.clock.now();
    const ticket = this.store.state().tickets[ticketId];
    if (!ticket) throw new Error(`unknown ticket ${ticketId}`);
    const input: Input = {
      id: this.ids.next("inp"),
      ticketId,
      kind: "text",
      ref: text.slice(0, 500),
      at: now,
    };
    const produced: AnyEvent[] = [ev.inputFannedOut(input, now)];
    if (ticket.state === "ended" && !ticket.stopped) produced.push(ev.ticketResumed(ticketId, now));
    effects.enqueue(this.ids.next("eff"), "deliver", { inputId: input.id }, now);
    return this.store.appendAll(produced);
  }

  /** 执行器报告：结束 assignment；ready/dropped 直接结束工单。 */
  report(report: Report): AnyEvent[] {
    const now = this.clock.now();
    this.store.append(ev.reportRecorded(report, now));
    const state = this.store.state();
    const produced: AnyEvent[] = [];
    const assignment = state.assignments[report.assignmentId];
    if (assignment && assignment.state !== "ended") {
      produced.push(ev.assignmentEnded(assignment.id, report.status, now));
      this.stopQuietly(assignment);
    }
    if (report.status === "ready" || report.status === "dropped") {
      const ticket = state.tickets[report.ticketId];
      if (ticket && ticket.state === "open") {
        produced.push(ev.ticketEnded(ticket.id, report.status, report.summary, now));
      }
    }
    return produced.length > 0 ? this.store.appendAll(produced) : [];
  }

  /** 运维重试：结束当前 assignment，并投递一条 retry 输入让工单重新排到执行器。 */
  retry(ticketId: string, effects: Effects): AnyEvent[] {
    const now = this.clock.now();
    const state = this.store.state();
    if (!state.tickets[ticketId]) throw new Error(`unknown ticket ${ticketId}`);
    const produced: AnyEvent[] = [];
    for (const assignment of Object.values(state.assignments)) {
      if (assignment.ticketId === ticketId && assignment.state !== "ended") {
        produced.push(ev.assignmentEnded(assignment.id, "retry", now));
        this.stopQuietly(assignment);
      }
    }
    produced.push(this.makeInput(ticketId, "retry", "operator retry", effects, now));
    return this.store.appendAll(produced);
  }

  /** 进程重启恢复：收口所有 running assignment，并留下恢复注记。 */
  recoverAfterRestart(effects: Effects): AnyEvent[] {
    const now = this.clock.now();
    const state = this.store.state();
    const produced: AnyEvent[] = [];
    const resumed = new Set<string>();
    for (const assignment of Object.values(state.assignments)) {
      if (assignment.state !== "running") continue;
      produced.push(ev.assignmentEnded(assignment.id, "host-restarted", now));
      if (resumed.has(assignment.ticketId)) continue;
      resumed.add(assignment.ticketId);
      produced.push(
        this.makeInput(
          assignment.ticketId,
          "resume",
          "host restarted; check directory, git and remote before repeating outside actions",
          effects,
          now,
        ),
      );
    }
    return produced.length > 0 ? this.store.appendAll(produced) : [];
  }

  private stopQuietly(assignment: Assignment): void {
    try {
      const result: unknown = this.executor.stop(assignment);
      if (result && typeof (result as Promise<void>).catch === "function") {
        void (result as Promise<void>).catch(() => undefined);
      }
    } catch {
      // 执行器已退出：忽略
    }
  }

  private makeInput(
    ticketId: string,
    kind: string,
    ref: string,
    effects: Effects,
    now: number,
  ): AnyEvent {
    const input: Input = {
      id: this.ids.next("inp"),
      ticketId,
      kind,
      ref,
      at: now,
    };
    effects.enqueue(this.ids.next("eff"), "deliver", { inputId: input.id }, now);
    return ev.inputFannedOut(input, now);
  }
}