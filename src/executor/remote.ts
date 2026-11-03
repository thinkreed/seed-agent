/**
 * RemoteExecutor：计算侧的执行器客户端。
 * 只发指令、只收报告；真正干活的是远端/本地 daemon。
 *
 * 间歇在线（文章 §5.2 BYOM）：记录已派工与未确认输入；设备重新上线后调用
 * recover() 重新拉起仍在跑的 Assignment 并补投未确认输入。
 */

import { existsSync, readFileSync } from "node:fs";

import type { Clock } from "../clock.ts";
import type { Assignment, Input, Report, ReportStatus, Ticket } from "../domain.ts";
import type { Executor } from "../ports.ts";
import type { DaemonEvent, DaemonRequest, DaemonResponse, Transport, WorkerSpec } from "./protocol.ts";

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
  /** 本机 recall 索引；launch 时把内容发给远端 daemon。 */
  readonly recallIndexPath?: string;
}

interface TrackedLaunch {
  readonly assignment: Assignment;
  readonly ticket: Ticket;
}

export class RemoteExecutor implements Executor {
  private readonly options: RemoteExecutorOptions;
  private readonly launched = new Map<string, TrackedLaunch>();
  private readonly queuedInputs = new Map<string, { ticket: Ticket; input: Input }>();
  private readonly stopped = new Set<string>();
  private counter = 0;

  constructor(options: RemoteExecutorOptions) {
    this.options = options;
    this.options.transport.onEvent((event) => this.onEvent(event));
  }

  async launch(assignment: Assignment, ticket: Ticket): Promise<void> {
    this.launched.set(assignment.id, { assignment, ticket });
    this.stopped.delete(assignment.id);
    const response = await this.send(this.launchRequest(assignment, ticket));
    if (!response.ok) throw new Error(`daemon launch failed: ${response.error}`);
  }

  async deliver(ticket: Ticket, input: Input): Promise<void> {
    this.queuedInputs.set(input.id, { ticket, input });
    const response = await this.send(this.deliverRequest(ticket, input));
    if (!response.ok) throw new Error(`daemon deliver failed: ${response.error}`);
    this.queuedInputs.delete(input.id);
  }

  async stop(assignment: Assignment): Promise<void> {
    this.stopped.add(assignment.id);
    this.launched.delete(assignment.id);
    const response = await this.send(stopRequest(assignment));
    if (!response.ok) throw new Error(`daemon stop failed: ${response.error}`);
  }

  /**
   * 设备重新上线后恢复：重新拉起未结束的 Assignment，并补投未确认输入。
   * 幂等方向是"以计算侧状态为准"；daemon 侧不需要持久状态。
   */
  async recover(): Promise<{ relaunched: number; redelivered: number }> {
    let relaunched = 0;
    for (const tracked of this.launched.values()) {
      if (this.stopped.has(tracked.assignment.id)) continue;
      const response = await this.send(this.launchRequest(tracked.assignment, tracked.ticket));
      if (response.ok) relaunched += 1;
    }
    let redelivered = 0;
    for (const item of [...this.queuedInputs.values()]) {
      const response = await this.send(this.deliverRequest(item.ticket, item.input));
      if (response.ok) {
        this.queuedInputs.delete(item.input.id);
        redelivered += 1;
      }
    }
    return { relaunched, redelivered };
  }

  closeAll(): void {
    this.options.transport.close();
  }

  private launchRequest(assignment: Assignment, ticket: Ticket): DaemonRequest {
    this.counter += 1;
    return {
      id: `req-${this.counter}`,
      cmd: "launch",
      assignmentId: assignment.id,
      ticketId: ticket.id,
      shortName: ticket.shortName,
      scope: ticket.mandate.scope,
      worker: this.options.worker,
      ...(this.options.prepare ? { prepare: this.options.prepare } : {}),
      ...(this.options.recallIndexPath && existsSync(this.options.recallIndexPath)
        ? { recallIndex: readFileSync(this.options.recallIndexPath, "utf8") }
        : {}),
    };
  }

  private deliverRequest(ticket: Ticket, input: Input): DaemonRequest {
    this.counter += 1;
    return {
      id: `req-${this.counter}`,
      cmd: "deliver",
      ticketId: ticket.id,
      inputId: input.id,
      kind: input.kind,
      ref: input.ref,
    };
  }

  private send(request: DaemonRequest): Promise<DaemonResponse> {
    return this.options.transport.send(request);
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

function stopRequest(assignment: Assignment): DaemonRequest {
  return {
    id: `req-stop-${assignment.id}`,
    cmd: "stop",
    ticketId: assignment.ticketId,
  };
}