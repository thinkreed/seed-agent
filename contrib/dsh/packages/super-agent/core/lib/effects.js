/** stored work：先落库、后执行、失败退避。副作用只能从这里出去。 */
export const DEFAULT_BACKOFF = {
    schedule: [2, 4, 8, 16, 32, 60],
    maxAttempts: 6,
};
export function backoffDelay(backoff, attempts) {
    if (attempts <= 0)
        return 0;
    const index = Math.min(attempts - 1, backoff.schedule.length - 1);
    return backoff.schedule[index] ?? 0;
}
export class Effects {
    handlers;
    store;
    clock;
    backoff;
    constructor(store, clock, handlers = {}, backoff = DEFAULT_BACKOFF) {
        this.store = store;
        this.clock = clock;
        this.handlers = new Map(Object.entries(handlers));
        this.backoff = backoff;
    }
    register(kind, handler) {
        this.handlers.set(kind, handler);
    }
    enqueue(id, kind, payload, at) {
        this.store.outboxEnqueue(id, kind, payload, at ?? this.clock.now());
        return id;
    }
    /** 执行所有到期项，返回 (产生的事件, 被丢弃的 id)。 */
    async drain() {
        const produced = [];
        const dropped = [];
        for (const item of this.store.outboxDue(this.clock.now())) {
            const handler = this.handlers.get(item.kind);
            if (!handler) {
                this.store.outboxMark(item.id, "dropped", item.attempts, this.clock.now(), "no-handler");
                dropped.push(item.id);
                continue;
            }
            const now = this.clock.now();
            let events;
            try {
                events = await handler(item);
            }
            catch (error) {
                const attempts = item.attempts + 1;
                if (attempts >= this.backoff.maxAttempts) {
                    this.store.outboxMark(item.id, "dropped", attempts, now, String(error));
                    dropped.push(item.id);
                }
                else {
                    this.store.outboxMark(item.id, "pending", attempts, now + backoffDelay(this.backoff, attempts), String(error));
                }
                continue;
            }
            this.store.outboxMark(item.id, "done", item.attempts, now);
            produced.push(...events);
        }
        return { produced, dropped };
    }
}
//# sourceMappingURL=effects.js.map