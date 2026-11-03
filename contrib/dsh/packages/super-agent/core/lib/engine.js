import { Actions } from "./actions.js";
import { ev } from "./builders.js";
import { handBack, unsubscribeFrom } from "./engine_control.js";
import { subscribedTickets } from "./domain.js";
import { Effects } from "./effects.js";
import { EvalRunner } from "./eval_runner.js";
import { gate } from "./policy.js";
export class Engine {
    store;
    clock;
    ids;
    assessor;
    executor;
    slots;
    effects;
    channels;
    evalRunner;
    actions;
    paused = false;
    constructor(options) {
        this.store = options.store;
        this.clock = options.clock;
        this.ids = options.ids;
        this.assessor = options.assessor;
        this.executor = options.executor;
        this.slots = options.slots ?? 4;
        this.channels = options.channels;
        this.actions = new Actions({
            store: this.store,
            clock: this.clock,
            ids: this.ids,
            executor: this.executor,
            channels: this.channels,
        });
        this.effects = new Effects(this.store, this.clock, {
            launch: (item) => this.actions.launch(item.payload.assignmentId),
            deliver: (item) => this.actions.deliver(item.payload.inputId),
            send: (item) => this.actions.send(item.payload.messageId),
        });
        this.evalRunner = new EvalRunner({
            store: this.store,
            clock: this.clock,
            ids: this.ids,
            assessor: this.assessor,
            effects: this.effects,
        });
        if (options.policy)
            this.append([ev.policyChanged(options.policy, this.clock.now())]);
    }
    get state() {
        return this.store.state();
    }
    ingest(trigger) {
        const now = this.clock.now();
        const state = this.state;
        if (state.triggers[trigger.id])
            return [];
        const threadIds = trigger.threadIds.length > 0 ? trigger.threadIds : [`${trigger.source}:default`];
        const normalized = { ...trigger, threadIds, at: trigger.at || now };
        const produced = [ev.triggerRecorded(normalized, now)];
        for (const threadId of threadIds) {
            if (!state.threads[threadId]) {
                produced.push(ev.threadDeclared({ id: threadId, source: trigger.source, at: now }, now));
            }
        }
        const gateResult = gate(state.policy, normalized);
        if (!gateResult.allowed) {
            produced.push(ev.triggerFiltered(normalized.id, "fast", gateResult.reason, now));
            produced.push(ev.dispositionRecorded(normalized.id, "filtered", now));
            return this.append(produced);
        }
        const fanOutTo = [...new Set(threadIds.flatMap((threadId) => subscribedTickets(state, threadId)))];
        if (fanOutTo.length > 0)
            return this.fanOut(normalized, fanOutTo, produced, now);
        return this.queueEval(normalized, threadIds[0], produced, now);
    }
    fanOut(trigger, ticketIds, produced, now) {
        for (const ticketId of ticketIds) {
            const input = {
                id: this.ids.next("inp"),
                ticketId,
                kind: "trigger",
                ref: trigger.id,
                at: now,
            };
            produced.push(ev.inputFannedOut(input, now));
            this.effects.enqueue(this.ids.next("eff"), "deliver", { inputId: input.id }, now);
        }
        produced.push(ev.dispositionRecorded(trigger.id, "fanned_out", now));
        return this.append(produced);
    }
    queueEval(trigger, threadId, produced, now) {
        const queued = Object.values(this.state.evals).find((item) => item.threadId === threadId && item.state === "queued");
        if (queued) {
            produced.push(ev.evalQueued({ ...queued, triggerIds: [...queued.triggerIds, trigger.id] }, now));
        }
        else {
            const evaluation = {
                id: this.ids.next("eval"),
                threadId,
                triggerIds: [...this.queuedTriggerIds(threadId), trigger.id],
                state: "queued",
                at: now,
            };
            produced.push(ev.evalQueued(evaluation, now));
        }
        produced.push(ev.dispositionRecorded(trigger.id, "queued", now));
        return this.append(produced);
    }
    queuedTriggerIds(threadId) {
        const state = this.state;
        return Object.values(state.triggers)
            .filter((item) => item.threadIds.includes(threadId) && state.dispositions[item.id] === "queued")
            .map((item) => item.id)
            .sort();
    }
    async tick() {
        if (this.paused)
            return [];
        const produced = [];
        const queued = Object.values(this.state.evals).filter((item) => item.state === "queued");
        if (queued.length > 0) {
            const batches = await Promise.all(queued.map((evaluation) => this.evalRunner.run(evaluation)));
            for (const batch of batches)
                produced.push(...batch);
        }
        produced.push(...this.actions.dispatch(this.slots, this.effects));
        const { produced: effectEvents } = await this.effects.drain();
        produced.push(...this.append(effectEvents));
        return produced;
    }
    personMessage(ticketId, text) {
        return this.actions.personMessage(ticketId, text, this.effects);
    }
    pause() { this.paused = true; }
    resume() { this.paused = false; }
    get isPaused() { return this.paused; }
    setPolicy(policy) { return this.actions.setPolicy(policy); }
    retry(ticketId) {
        return this.actions.retry(ticketId, this.effects);
    }
    recoverAfterRestart() {
        return this.actions.recoverAfterRestart(this.effects);
    }
    report(report) {
        return this.actions.report(report);
    }
    /** Worker 取消订阅：之后同一 Thread 的事件不再直通该工单（回到 Router 评估）。 */
    unsubscribe(ticketId, threadId) {
        return unsubscribeFrom(this.state, this.clock, (events) => this.append(events), ticketId, threadId);
    }
    /** Worker 交回 Router：取消订阅并把最新事件重新入评估队列（文章 §3.2）。 */
    handback(ticketId, _reason = "") {
        return handBack(this.state, this.clock, this.ids, (events) => this.append(events), ticketId);
    }
    append(events) {
        return events.length > 0 ? this.store.appendAll(events) : [];
    }
}
//# sourceMappingURL=engine.js.map