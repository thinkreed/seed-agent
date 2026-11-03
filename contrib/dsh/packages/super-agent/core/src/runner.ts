/**
 * SourceRunner：把 Source 的 poll 结果喂进引擎，并逐源记录位点与失败。
 * 一个 Source 出错不影响其它 Source（隔离）。
 */

import type { Clock } from "./clock.ts";
import type { Engine } from "./engine.ts";
import type { Source } from "./ports.ts";
import { recordSourceFailure, recordSourceRecovery } from "./source_health.ts";
import type { SqliteStore } from "./store.ts";

export interface SourceFailure {
  readonly source: string;
  readonly error: string;
}

export interface PollReport {
  readonly ingested: number;
  readonly failures: readonly SourceFailure[];
}

export class SourceRunner {
  private readonly sources: Source[];
  private readonly engine: Engine;
  private readonly store: SqliteStore;
  private readonly clock: Clock;
  private readonly failed = new Set<string>();
  private readonly onTrigger: ((trigger: import("./domain.ts").Trigger) => void) | undefined;
  private readonly onIngested: ((trigger: import("./domain.ts").Trigger) => void) | undefined;

  constructor(options: {
    sources: readonly Source[];
    engine: Engine;
    store: SqliteStore;
    clock: Clock;
    /** 观测回调：Router 用它看到所有事件（含随后直通 Worker 的）。 */
    onTrigger?: (trigger: import("./domain.ts").Trigger) => void;
    /** 新事件完成入账后的回调（投机执行只对真正的新事件触发一次）。 */
    onIngested?: (trigger: import("./domain.ts").Trigger) => void;
  }) {
    this.sources = [...options.sources];
    this.engine = options.engine;
    this.store = options.store;
    this.clock = options.clock;
    this.onTrigger = options.onTrigger;
    this.onIngested = options.onIngested;
  }

  /** 轮询所有 Source：各自独立容错。 */
  async pollOnce(): Promise<PollReport> {
    let ingested = 0;
    const failures: SourceFailure[] = [];
    for (const source of this.sources) {
      try {
        const batch = await source.poll();
        if (this.failed.delete(source.name)) {
          recordSourceRecovery(this.store, this.clock, source.name);
        }
        for (const trigger of batch) {
          this.onTrigger?.(trigger);
          const produced = this.engine.ingest(trigger);
          if (produced.length === 0) continue; // 已入账过的 Trigger 不算新事件
          ingested += 1;
          this.store.cursorSet(source.name, trigger.id, this.clock.now());
          this.onIngested?.(trigger);
        }
      } catch (error) {
        failures.push({ source: source.name, error: String(error) });
        if (!this.failed.has(source.name)) {
          this.failed.add(source.name);
          recordSourceFailure(this.store, this.clock, source.name, String(error));
        }
      }
    }
    return { ingested, failures };
  }

  /** 轮询直到所有 Source 都没有新事件。失败按来源去重（保留最后一次错误）。 */
  async drain(maxRounds = 100): Promise<PollReport> {
    let ingested = 0;
    const failures = new Map<string, SourceFailure>();
    for (let round = 0; round < maxRounds; round += 1) {
      const report = await this.pollOnce();
      ingested += report.ingested;
      for (const failure of report.failures) failures.set(failure.source, failure);
      if (report.ingested === 0) return { ingested, failures: [...failures.values()] };
    }
    throw new Error("sources did not drain");
  }
}