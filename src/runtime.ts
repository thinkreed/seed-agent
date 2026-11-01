/** 运行时装配：唯一把端口接到引擎上的地方。 */

import type { Clock } from "./clock.ts";
import { SystemClock } from "./clock.ts";
import type { Policy } from "./domain.ts";
import { Engine } from "./engine.ts";
import type { IdFactory } from "./ids.ts";
import { SeqIds } from "./ids.ts";
import { defaultPolicy } from "./policy.ts";
import type { Assessor, Executor } from "./ports.ts";
import { SqliteStore } from "./store.ts";

export interface RuntimeConfig {
  readonly dbPath?: string;
  readonly slots?: number;
  readonly policy?: Policy;
}

export interface RuntimeOptions {
  readonly assessor: Assessor;
  readonly executor: Executor;
  readonly config?: RuntimeConfig;
  readonly clock?: Clock;
  readonly ids?: IdFactory;
}

export class Runtime {
  readonly engine: Engine;
  readonly store: SqliteStore;
  readonly clock: Clock;
  readonly config: RuntimeConfig;

  constructor(engine: Engine, store: SqliteStore, clock: Clock, config: RuntimeConfig) {
    this.engine = engine;
    this.store = store;
    this.clock = clock;
    this.config = config;
  }

  static build(options: RuntimeOptions): Runtime {
    const config = options.config ?? {};
    const clock = options.clock ?? new SystemClock();
    const store = new SqliteStore(config.dbPath ?? ":memory:");
    const engine = new Engine({
      store,
      clock,
      ids: options.ids ?? new SeqIds(),
      assessor: options.assessor,
      executor: options.executor,
      policy: config.policy ?? defaultPolicy(),
      slots: config.slots ?? 4,
    });
    return new Runtime(engine, store, clock, config);
  }

  /** 跑到没有新事件为止；返回 tick 次数。 */
  async tickUntilIdle(maxTicks = 100): Promise<number> {
    for (let tick = 1; tick <= maxTicks; tick += 1) {
      const before = this.store.lastSeq();
      await this.engine.tick();
      if (this.store.lastSeq() === before) return tick;
    }
    throw new Error("runtime did not settle");
  }

  close(): void {
    this.store.close();
  }
}