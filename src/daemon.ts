/**
 * Daemon：进程内的主循环 —— 轮询 Source、驱动引擎、执行副作用。
 * 与"存算分离"对应：状态在 Store，循环本身无状态，可随时重启。
 */

import type { Clock } from "./clock.ts";
import type { Engine } from "./engine.ts";
import type { SourceRunner } from "./runner.ts";
import type { SqliteStore } from "./store.ts";

export interface RoundReport {
  readonly ingested: number;
  readonly events: number;
  readonly failures: number;
}

export interface WatchdogBridge {
  check(state: import("./domain.ts").State): Promise<import("./watchdog.ts").WatchdogReport>;
  apply(report: import("./watchdog.ts").WatchdogReport): unknown;
}

export interface DaemonOptions {
  readonly runner: SourceRunner;
  readonly engine: Engine;
  readonly store: SqliteStore;
  readonly clock: Clock;
  readonly intervalMs?: number;
  readonly sleep?: (ms: number) => Promise<void>;
  readonly watchdog?: WatchdogBridge;
  readonly afterRound?: () => void | Promise<void>;
}

export class Daemon {
  private readonly options: DaemonOptions;
  private running = false;
  private rounds = 0;

  constructor(options: DaemonOptions) {
    this.options = options;
  }

  /** 跑一轮：收事件 -> 驱动引擎 -> 巡检。返回这一轮的统计。 */
  async runRound(): Promise<RoundReport> {
    const poll = await this.options.runner.pollOnce();
    const before = this.options.store.lastSeq();
    await this.options.engine.tick();
    if (this.options.watchdog) {
      const report = await this.options.watchdog.check(this.options.store.state());
      this.options.watchdog.apply(report);
    }
    if (this.options.afterRound) await this.options.afterRound();
    const events = this.options.store.lastSeq() - before;
    this.rounds += 1;
    return { ingested: poll.ingested, events, failures: poll.failures.length };
  }

  /** 常驻循环，直到 stop()。 */
  async run(maxRounds = Number.POSITIVE_INFINITY): Promise<number> {
    this.running = true;
    const sleep = this.options.sleep ?? defaultSleep;
    const interval = this.options.intervalMs ?? 1000;
    while (this.running && this.rounds < maxRounds) {
      const report = await this.runRound();
      if (!this.running) break;
      if (report.ingested === 0 && report.events === 0) await sleep(interval);
    }
    return this.rounds;
  }

  stop(): void {
    this.running = false;
  }

  get roundCount(): number {
    return this.rounds;
  }
}

function defaultSleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}