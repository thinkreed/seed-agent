/**
 * WorkerSession：一个可被新消息唤醒的执行会话。
 *
 * 全双工语义：turn 进行中收到的新输入先入队，当前 turn 结束后立刻用它开下一轮，
 * 不需要等下一次外部调度。
 */

import type { Clock } from "./clock.ts";
import type { Report, Ticket, Trigger } from "./domain.ts";
import type { JobRegistry } from "./jobs.ts";
import type { ModelClient } from "./model.ts";
import { type ReactTool, ReactLoop } from "./react.ts";

export interface WorkerSessionOptions {
  readonly model: ModelClient;
  readonly tools: Readonly<Record<string, ReactTool>>;
  readonly jobs: JobRegistry;
  readonly clock: Clock;
  readonly maxSteps?: number;
  readonly maxTurns?: number;
}

export class WorkerSession {
  private readonly loop: ReactLoop;
  private readonly maxTurns: number;
  private readonly inbox: Trigger[] = [];

  constructor(options: WorkerSessionOptions) {
    this.loop = new ReactLoop({
      model: options.model,
      tools: options.tools,
      jobs: options.jobs,
      clock: options.clock,
      ...(options.maxSteps === undefined ? {} : { maxSteps: options.maxSteps }),
    });
    this.maxTurns = options.maxTurns ?? 8;
  }

  /** 外部投递：turn 进行中也不会丢，进队列等当前 turn 结束。 */
  deliver(input: Trigger): void {
    this.inbox.push(input);
  }

  get queued(): number {
    return this.inbox.length;
  }

  async run(ticket: Ticket, initial: readonly Trigger[] = []): Promise<Report[]> {
    const reports: Report[] = [];
    let pending = [...initial];
    for (let turn = 0; turn < this.maxTurns; turn += 1) {
      reports.push(await this.loop.run(ticket, pending));
      if (this.inbox.length === 0) return reports;
      if (turn + 1 >= this.maxTurns) return reports; // 留待下一次唤醒，不丢消息
      pending = this.inbox.splice(0, this.inbox.length);
    }
    return reports;
  }
}