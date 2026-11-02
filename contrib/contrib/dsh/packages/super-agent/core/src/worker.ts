/**
 * WorkerSession：一个可被新消息唤醒的执行会话。
 *
 * 全双工语义：turn 进行中收到的新输入先入队，当前 turn 结束后立刻用它开下一轮，
 * 不需要等下一次外部调度。
 *
 * 后台任务完成后，结果作为一条新的会话输入（source=job）回到同一会话，
 * 由模型在下一轮消化（文章 §4.1），而不是要求模型反复轮询 status()。
 */

import type { Clock } from "./clock.ts";
import type { Report, Ticket, Trigger } from "./domain.ts";
import type { JobNotice, JobRegistry } from "./jobs.ts";
import type { ModelClient } from "./model.ts";
import { type ReactTool, ReactLoop } from "./react.ts";

export interface WorkerSessionOptions {
  readonly model: ModelClient;
  readonly tools: Readonly<Record<string, ReactTool>>;
  readonly jobs: JobRegistry;
  readonly clock: Clock;
  readonly maxSteps?: number;
  readonly maxTurns?: number;
  /** 有后台任务在跑时等它完成再开下一轮（默认 true）。 */
  readonly waitForJobs?: boolean;
}

export class WorkerSession {
  private readonly loop: ReactLoop;
  private readonly jobs: JobRegistry;
  private readonly clock: Clock;
  private readonly maxTurns: number;
  private readonly waitForJobs: boolean;
  private readonly inbox: Trigger[] = [];

  constructor(options: WorkerSessionOptions) {
    this.loop = new ReactLoop({
      model: options.model,
      tools: options.tools,
      jobs: options.jobs,
      clock: options.clock,
      ...(options.maxSteps === undefined ? {} : { maxSteps: options.maxSteps }),
      nextInputs: () => this.inbox.splice(0, this.inbox.length).map((input) => input.text),
    });
    this.jobs = options.jobs;
    this.clock = options.clock;
    this.maxTurns = options.maxTurns ?? 8;
    this.waitForJobs = options.waitForJobs ?? true;
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
    let pending: Trigger[] = [...initial];
    for (let turn = 0; turn < this.maxTurns; turn += 1) {
      reports.push(await this.loop.run(ticket, pending));
      let next = this.inbox.splice(0, this.inbox.length);
      if (next.length === 0 && this.waitForJobs) {
        const notice = await this.jobs.nextNotice(ticket.id);
        if (!notice) return reports;
        next = [this.jobInput(ticket, notice)];
      }
      if (next.length === 0) return reports;
      if (turn + 1 >= this.maxTurns) {
        // 留待下一次唤醒，不丢消息。
        this.inbox.push(...next);
        return reports;
      }
      pending = next;
    }
    return reports;
  }

  /** 把后台任务完成通知变成一条会话输入。 */
  private jobInput(ticket: Ticket, notice: JobNotice): Trigger {
    const detail = notice.error
      ? `error: ${notice.error}`
      : JSON.stringify(notice.result ?? null).slice(0, 4000);
    return {
      id: `${notice.jobId}:${notice.state}:${this.clock.now()}`,
      source: "job",
      actor: "system",
      text: `后台任务 ${notice.jobId} ${notice.state}: ${detail}`,
      threadIds: ticket.threadIds,
      channelIds: [],
      at: this.clock.now(),
    };
  }
}