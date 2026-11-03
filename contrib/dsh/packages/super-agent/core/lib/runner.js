/**
 * SourceRunner：把 Source 的 poll 结果喂进引擎，并逐源记录位点与失败。
 * 一个 Source 出错不影响其它 Source（隔离）。
 */
import { recordSourceFailure, recordSourceRecovery } from "./source_health.js";
export class SourceRunner {
    sources;
    engine;
    store;
    clock;
    failed = new Set();
    onTrigger;
    onIngested;
    constructor(options) {
        this.sources = [...options.sources];
        this.engine = options.engine;
        this.store = options.store;
        this.clock = options.clock;
        this.onTrigger = options.onTrigger;
        this.onIngested = options.onIngested;
    }
    /** 轮询所有 Source：各自独立容错。 */
    async pollOnce() {
        let ingested = 0;
        const failures = [];
        for (const source of this.sources) {
            try {
                const batch = await source.poll();
                if (this.failed.delete(source.name)) {
                    recordSourceRecovery(this.store, this.clock, source.name);
                }
                for (const trigger of batch) {
                    this.onTrigger?.(trigger);
                    const produced = this.engine.ingest(trigger);
                    if (produced.length === 0)
                        continue; // 已入账过的 Trigger 不算新事件
                    ingested += 1;
                    this.store.cursorSet(source.name, trigger.id, this.clock.now());
                    this.onIngested?.(trigger);
                }
            }
            catch (error) {
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
    async drain(maxRounds = 100) {
        let ingested = 0;
        const failures = new Map();
        for (let round = 0; round < maxRounds; round += 1) {
            const report = await this.pollOnce();
            ingested += report.ingested;
            for (const failure of report.failures)
                failures.set(failure.source, failure);
            if (report.ingested === 0)
                return { ingested, failures: [...failures.values()] };
        }
        throw new Error("sources did not drain");
    }
}
//# sourceMappingURL=runner.js.map