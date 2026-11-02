/**
 * 后台任务注册表：异步 ReAct 的底座。
 *
 * - start() 立即返回 jobId，任务在后台跑；
 * - 完成/失败/超时都会留下记录与待消费通知；
 * - stop() 通过 AbortSignal 协作取消；
 * - tick() 负责把超过时限的任务判死（默认 30 分钟）。
 */

import type { Clock } from "./clock.ts";

export type JobState = "running" | "done" | "failed" | "stopped";

export interface JobRecord {
  readonly id: string;
  readonly kind: string;
  readonly ticketId: string;
  readonly state: JobState;
  readonly startedAt: number;
  finishedAt?: number;
  result?: unknown;
  error?: string;
}

export interface JobNotice {
  readonly jobId: string;
  readonly ticketId: string;
  readonly state: JobState;
  readonly result?: unknown;
  readonly error?: string;
}

interface RunningJob {
  record: JobRecord;
  controller: AbortController;
  timer: ReturnType<typeof setTimeout> | undefined;
}

export class JobRegistry {
  private readonly clock: Clock;
  private readonly maxRunSeconds: number;
  private readonly jobs = new Map<string, RunningJob>();
  private readonly notices: JobNotice[] = [];
  private readonly waiters = new Map<string, ((notice: JobNotice) => void)[]>();
  private counter = 0;

  constructor(clock: Clock, options: { maxRunSeconds?: number } = {}) {
    this.clock = clock;
    this.maxRunSeconds = options.maxRunSeconds ?? 1800;
  }

  start(kind: string, ticketId: string, run: (signal: AbortSignal) => Promise<unknown>): string {
    this.counter += 1;
    const id = `job-${String(this.counter).padStart(6, "0")}`;
    const controller = new AbortController();
    const record: JobRecord = {
      id,
      kind,
      ticketId,
      state: "running",
      startedAt: this.clock.now(),
    };
    const timer = this.deadlineTimer(id);
    this.jobs.set(id, { record, controller, timer });

    void Promise.resolve()
      .then(() => {
        if (controller.signal.aborted) return undefined;
        return run(controller.signal);
      })
      .then(
        (result) => this.settle(id, "done", result),
        (error: unknown) => this.settle(id, "failed", undefined, String(error)),
      );
    return id;
  }

  stop(id: string): boolean {
    const job = this.jobs.get(id);
    if (!job || job.record.state !== "running") return false;
    job.controller.abort();
    this.settle(id, "stopped");
    return true;
  }

  /** 把超时未完成的任务判死。 */
  tick(): void {
    for (const job of this.jobs.values()) {
      if (job.record.state !== "running") continue;
      if (this.clock.now() - job.record.startedAt >= this.maxRunSeconds) {
        job.controller.abort();
        this.settle(job.record.id, "stopped", undefined, "deadline");
      }
    }
  }

  get(id: string): JobRecord | undefined {
    return this.jobs.get(id)?.record;
  }

  running(): JobRecord[] {
    return [...this.jobs.values()]
      .map((job) => job.record)
      .filter((record) => record.state === "running");
  }

  /** 某个工单仍在后台运行的任务。 */
  runningFor(ticketId: string): JobRecord[] {
    return this.running().filter((record) => record.ticketId === ticketId);
  }

  hasPending(ticketId: string): boolean {
    return this.notices.some((notice) => notice.ticketId === ticketId);
  }

  /**
   * 等待该工单的下一条完成通知（文章 §4.1：结果作为新事件回到会话）。
   * 没有待消费通知且没有在跑任务时返回 undefined，避免空等。
   */
  nextNotice(ticketId: string): Promise<JobNotice | undefined> {
    const index = this.notices.findIndex((notice) => notice.ticketId === ticketId);
    if (index >= 0) return Promise.resolve(this.notices.splice(index, 1)[0]);
    if (this.runningFor(ticketId).length === 0) return Promise.resolve(undefined);
    return new Promise((resolve) => {
      const list = this.waiters.get(ticketId) ?? [];
      list.push(resolve);
      this.waiters.set(ticketId, list);
    });
  }

  /** 取走尚未消费的完成通知（供 ReAct 循环注入 observation）。 */
  drainNotices(): JobNotice[] {
    return this.notices.splice(0, this.notices.length);
  }

  private settle(id: string, state: JobState, result?: unknown, error?: string): void {
    const job = this.jobs.get(id);
    if (!job || job.record.state !== "running") return;
    if (job.timer) clearTimeout(job.timer);
    job.record = {
      ...job.record,
      state,
      finishedAt: this.clock.now(),
      ...(result === undefined ? {} : { result }),
      ...(error === undefined ? {} : { error }),
    };
    this.jobs.set(id, job);
    const notice: JobNotice = {
      jobId: id,
      ticketId: job.record.ticketId,
      state,
      ...(result === undefined ? {} : { result }),
      ...(error === undefined ? {} : { error }),
    };
    const waiter = this.waiters.get(notice.ticketId)?.shift();
    if (waiter) {
      if ((this.waiters.get(notice.ticketId)?.length ?? 0) === 0) this.waiters.delete(notice.ticketId);
      waiter(notice);
      return;
    }
    this.notices.push(notice);
  }

  private deadlineTimer(id: string): ReturnType<typeof setTimeout> | undefined {
    if (this.maxRunSeconds === Number.POSITIVE_INFINITY) return undefined;
    const timer = setTimeout(() => {
      const job = this.jobs.get(id);
      if (job?.record.state === "running") {
        job.controller.abort();
        this.settle(id, "stopped", undefined, "deadline");
      }
    }, this.maxRunSeconds * 1000);
    // 测试环境不需要让定时器挂住进程
    if (typeof timer === "object" && "unref" in timer) timer.unref();
    return timer;
  }
}