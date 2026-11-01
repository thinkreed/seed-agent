/**
 * SourceRunner：把 Source 的 poll 结果喂进引擎，并逐源记录位点与失败。
 * 一个 Source 出错不影响其它 Source（隔离）。
 */

import type { Clock } from "./clock.ts";
import type { Engine } from "./engine.ts";
import type { Source } from "./ports.ts";
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

  constructor(options: {
    sources: readonly Source[];
    engine: Engine;
    store: SqliteStore;
    clock: Clock;
  }) {
    this.sources = [...options.sources];
    this.engine = options.engine;
    this.store = options.store;
    this.clock = options.clock;
  }

  /** 轮询所有 Source：各自独立容错。 */
  pollOnce(): PollReport {
    let ingested = 0;
    const failures: SourceFailure[] = [];
    for (const source of this.sources) {
      try {
        const batch = source.poll();
        for (const trigger of batch) {
          this.engine.ingest(trigger);
          ingested += 1;
          this.store.cursorSet(source.name, trigger.id, this.clock.now());
        }
      } catch (error) {
        failures.push({ source: source.name, error: String(error) });
      }
    }
    return { ingested, failures };
  }

  /** 轮询直到所有 Source 都没有新事件。失败按来源去重（保留最后一次错误）。 */
  drain(maxRounds = 100): PollReport {
    let ingested = 0;
    const failures = new Map<string, SourceFailure>();
    for (let round = 0; round < maxRounds; round += 1) {
      const report = this.pollOnce();
      ingested += report.ingested;
      for (const failure of report.failures) failures.set(failure.source, failure);
      if (report.ingested === 0) return { ingested, failures: [...failures.values()] };
    }
    throw new Error("sources did not drain");
  }
}