/**
 * 投机执行（文章 §3.4）：后台先做，有价值才交付；没价值静默丢弃。
 *
 * 与具体执行器解耦：runner 只负责"尝试"，Speculator 负责来源策略、去重、
 * 并发上限、超时与"只交付有价值结果"的闸门。
 */
import { SystemClock } from "./clock.js";
export class Speculator {
    runner;
    deliver;
    options;
    now;
    seen = new Set();
    history = [];
    active = 0;
    skipped = 0;
    failed = 0;
    constructor(settings) {
        this.runner = settings.runner;
        this.deliver = settings.deliver;
        this.options = settings.options;
        this.now = settings.now ?? (() => new SystemClock().now());
    }
    shouldRun(candidate) {
        if (!this.options.sources.includes(candidate.source))
            return false;
        if (this.seen.has(candidate.id))
            return false;
        if (this.active >= (this.options.maxConcurrent ?? 1))
            return false;
        return true;
    }
    /** 后台尝试；返回 undefined 表示按策略跳过（来源不匹配/重复/并发已满）。 */
    async run(candidate) {
        if (this.active >= (this.options.maxConcurrent ?? 1)) {
            this.skipped += 1;
            return undefined;
        }
        if (this.seen.has(candidate.id)) {
            this.skipped += 1;
            return undefined;
        }
        this.seen.add(candidate.id);
        if (this.seen.size > (this.options.dedupeLimit ?? 200)) {
            const oldest = this.seen.values().next().value;
            if (oldest)
                this.seen.delete(oldest);
        }
        this.active += 1;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), this.options.timeoutMs ?? 300_000);
        let verdict;
        try {
            const timedOut = new Promise((_, reject) => {
                controller.signal.addEventListener("abort", () => reject(new Error("speculation timeout")), {
                    once: true,
                });
            });
            verdict = await Promise.race([this.runner.run(candidate, controller.signal), timedOut]);
        }
        catch (error) {
            this.failed += 1;
            this.active -= 1;
            clearTimeout(timeout);
            const outcome = {
                candidateId: candidate.id,
                source: candidate.source,
                delivered: false,
                summary: `discarded: ${String(error).slice(0, 200)}`,
                at: this.now(),
            };
            this.history.push(outcome);
            return outcome;
        }
        clearTimeout(timeout);
        this.active -= 1;
        let delivered = false;
        if (verdict.deliver && verdict.summary.trim()) {
            try {
                await this.deliver(candidate, verdict);
                delivered = true;
            }
            catch {
                delivered = false;
            }
        }
        const outcome = {
            candidateId: candidate.id,
            source: candidate.source,
            delivered,
            summary: verdict.summary.slice(0, 500),
            at: this.now(),
        };
        this.history.push(outcome);
        if (this.history.length > 100)
            this.history.shift();
        return outcome;
    }
    get outcomes() {
        return this.history;
    }
    stats() {
        return {
            active: this.active,
            skipped: this.skipped,
            failed: this.failed,
            delivered: this.history.filter((item) => item.delivered).length,
            total: this.history.length,
        };
    }
}
//# sourceMappingURL=speculation.js.map