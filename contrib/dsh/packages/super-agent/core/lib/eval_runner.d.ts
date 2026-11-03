/** 评估执行：把一批 Trigger 交给 Assessment（模型侧），并把 Decision 落成事件。 */
import type { Clock } from "./clock.ts";
import type { Eval } from "./domain.ts";
import type { Effects } from "./effects.ts";
import type { AnyEvent } from "./events.ts";
import type { IdFactory } from "./ids.ts";
import type { Assessor } from "./ports.ts";
import type { SqliteStore } from "./store.ts";
export interface EvalRunnerOptions {
    readonly store: SqliteStore;
    readonly clock: Clock;
    readonly ids: IdFactory;
    readonly assessor: Assessor;
    /** 回复决策需要把 message.queued 的发送放进 outbox。 */
    readonly effects?: Effects;
}
export declare class EvalRunner {
    private readonly store;
    private readonly clock;
    private readonly ids;
    private readonly assessor;
    private readonly effects;
    constructor(options: EvalRunnerOptions);
    run(evaluation: Eval): Promise<AnyEvent[]>;
    private apply;
    private openTicket;
}
