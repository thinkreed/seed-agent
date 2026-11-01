/**
 * RemoteExecutor：计算侧的执行器客户端。
 * 只发指令、只收报告；真正干活的是远端/本地 daemon。
 */

import type { Clock } from "../clock.ts";
import type { Assignment, Input, Report, ReportStatus, Ticket } from "../domain.ts";
import type { Executor } from "../ports.ts";
import type { DaemonEvent, Transport, WorkerSpec } from "./protocol.ts";

const STATUSES: ReadonlySet<string> = new Set([
  "progress",
  "waiting",
  "ready",
  "blocked",
  "failed",
  "dropped",
]);

export interface RemoteExecutorOptions {
  readonly transport: Transport;
  readonly clock: Clock;
  readonly report: (report: Report) => void;
  readonly worker: WorkerSpec;
  readonly prepare?: WorkerSpec;
}

export class RemoteExecutor implements Executor {
  private readonly options: RemoteExecutorOptions;
  private readonly pending = new Map<string, string>(); // assignmentId -> ticketId
  private counter = 0;

  constructor(options: RemoteExecutorOptions) {
    this.options = options;
    this.options.transport.onEvent((event) => this.onEvent(event));
  }

  async launch(assignment: Assignment, ticket: Ticket): Promise<void> {
    this.pending.set(assignment.id, ticket.id);
    this.counter += 1;
    const response = await this.options.transport.send({
      id: `req-${this.counter}`,
      cmd: "launch",
      assignmentId: assignment.id,
      ticketId: ticket.id,
      shortName: ticket.shortName,
      scope: ticket.mandate.scope,
      worker: this.options.worker,
      ...(this.options.prepare ? { prepare: this.options.prepare } : {}),
    });
    if (!response.ok) throw new Error(`daemon launch failed: ${response.error}`);
  }

  async deliver(ticket: Ticket, input: Input): Promise<void> {
    this.counter += 1;
    const response = await this.options.transport.send({
      id: `req-${this.counter}`,
      cmd: "deliver",
      ticketId: ticket.id,
      inputId: input.id,
      kind: input.kind,
      ref: input.ref,
    });
    if (!response.ok) throw new Error(`daemon deliver failed: ${response.error}`);
  }

  async stop(assignment: Assignment): Promise<void> {
    this.counter += 1;
    const response = await this.options.transport.send({
      id: `req-${this.counter}`,
      cmd: "stop",
      ticketId: assignment.ticketId,
    });
    if (!response.ok) throw new Error(`daemon stop failed: ${response.error}`);
  }

  private onEvent(event: DaemonEvent): void {
    if (event.type !== "report") return;
    if (!STATUSES.has(event.status)) return;
    this.options.report({
      ticketId: event.ticketId,
      assignmentId: event.assignmentId,
      status: event.status as ReportStatus,
      summary: event.summary,
      at: event.at || this.options.clock.now(),
    });
  }
}