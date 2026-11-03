/** 运行时装配：唯一把端口接到引擎上的地方。 */
import { SystemClock } from "./clock.js";
import { Engine } from "./engine.js";
import { SeqIds } from "./ids.js";
import { defaultPolicy } from "./policy.js";
import { stateIds } from "./state_ids.js";
import { SqliteStore } from "./store.js";
export class Runtime {
    engine;
    store;
    clock;
    config;
    constructor(engine, store, clock, config) {
        this.engine = engine;
        this.store = store;
        this.clock = clock;
        this.config = config;
    }
    static build(options) {
        const config = options.config ?? {};
        const clock = options.clock ?? new SystemClock();
        const store = new SqliteStore(config.dbPath ?? ":memory:");
        const ids = options.ids ?? new SeqIds([...stateIds(store.state()), ...store.outboxIds()]);
        const engine = new Engine({
            store,
            clock,
            ids,
            assessor: options.assessor,
            executor: options.executor,
            channels: config.channels,
            policy: config.policy ?? defaultPolicy(),
            slots: config.slots ?? 4,
        });
        return new Runtime(engine, store, clock, config);
    }
    /** 跑到没有新事件为止；返回 tick 次数。 */
    async tickUntilIdle(maxTicks = 100) {
        for (let tick = 1; tick <= maxTicks; tick += 1) {
            const before = this.store.lastSeq();
            await this.engine.tick();
            if (this.store.lastSeq() === before)
                return tick;
        }
        throw new Error("runtime did not settle");
    }
    /** 没有在跑的 assignment、没有排队 Eval、没有待执行副作用。 */
    isSettled() {
        const state = this.engine.state;
        const running = Object.values(state.assignments).some((item) => item.state !== "ended");
        const queued = Object.values(state.evals).some((item) => item.state === "queued");
        return !running && !queued && !this.store.outboxHasPending();
    }
    close() {
        this.store.close();
    }
}
//# sourceMappingURL=runtime.js.map