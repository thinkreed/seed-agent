/**
 * Daemon：进程内的主循环 —— 轮询 Source、驱动引擎、执行副作用。
 * 与"存算分离"对应：状态在 Store，循环本身无状态，可随时重启。
 */
export class Daemon {
    options;
    running = false;
    rounds = 0;
    lastWatchdogAt = Number.NEGATIVE_INFINITY;
    constructor(options) {
        this.options = options;
    }
    /** 跑一轮：收事件 -> 驱动引擎 -> 巡检。返回这一轮的统计。 */
    async runRound() {
        const poll = await this.options.runner.pollOnce();
        const before = this.options.store.lastSeq();
        await this.options.engine.tick();
        const now = this.options.clock.now();
        const everySeconds = (this.options.watchdogIntervalMs ?? 60_000) / 1000;
        if (this.options.watchdog && now - this.lastWatchdogAt >= everySeconds) {
            this.lastWatchdogAt = now;
            const report = await this.options.watchdog.check(this.options.store.state());
            this.options.watchdog.apply(report);
        }
        if (this.options.afterRound)
            await this.options.afterRound();
        const events = this.options.store.lastSeq() - before;
        this.rounds += 1;
        return { ingested: poll.ingested, events, failures: poll.failures.length };
    }
    /** 常驻循环，直到 stop()。 */
    async run(maxRounds = Number.POSITIVE_INFINITY) {
        this.running = true;
        const sleep = this.options.sleep ?? defaultSleep;
        const interval = this.options.intervalMs ?? 1000;
        while (this.running && this.rounds < maxRounds) {
            const report = await this.runRound();
            if (!this.running)
                break;
            if (report.ingested === 0 && report.events === 0)
                await sleep(interval);
        }
        return this.rounds;
    }
    stop() {
        this.running = false;
    }
    get roundCount() {
        return this.rounds;
    }
}
function defaultSleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}
//# sourceMappingURL=daemon.js.map