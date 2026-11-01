/** 派工与 effects 处理器：把"要做的事"变成事件，副作用经 outbox。 */

import type { Clock } from "./clock.ts";
import { ev } from "./builders.ts";
import type { Assignment, Ticket } from "./domain.ts";
import { openAssignment } from "./domain.ts";
import type { Effects } from "./effects.ts";
import type { AnyEvent } from "./events.ts";
import type { IdFactory } from "./ids.ts";
import type { Executor } from "./ports.ts";
import type { SqliteStore } from "./store.ts";

export interface ActionsOptions {
  readonly store: SqliteStore;
  readonly clock: Clock;
  readonly ids: IdFactory;
  readonly executor: Executor;
}

export class Actions {
  private readonly store: SqliteStore;
  private readonly clock: Clock;
  private readonly ids: IdFactory;
  private readonly executor: Executor;

  constructor(options: ActionsOptions) {
    this.store = options.store;
    this.clock = options.clock;
    this.ids = options.ids;
    this.executor = options.executor;
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
}