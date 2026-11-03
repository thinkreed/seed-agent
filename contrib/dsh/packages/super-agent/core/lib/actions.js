/** 派工与 effects 处理器：把"要做的事"变成事件，副作用经 outbox。 */
import { ev } from "./builders.js";
import { openAssignment } from "./domain.js";
export class Actions {
    store;
    clock;
    ids;
    executor;
    channels;
    constructor(options) {
        this.store = options.store;
        this.clock = options.clock;
        this.ids = options.ids;
        this.executor = options.executor;
        this.channels = options.channels;
    }
    /** 给空闲工单派活：受并发槽限制。只有"从未派过工"或"有新输入未投递"的工单才启动新 Assignment。
     */
    dispatch(slots, effects) {
        const now = this.clock.now();
        const state = this.store.state();
        const live = Object.values(state.assignments).filter((item) => item.state !== "ended");
        let capacity = slots - live.length;
        const produced = [];
        for (const ticket of Object.values(state.tickets).sort((a, b) => a.id.localeCompare(b.id))) {
            if (capacity <= 0)
                break;
            if (ticket.state !== "open" || ticket.stopped)
                continue;
            if (openAssignment(state, ticket.id))
                continue;
            const neverAssigned = !Object.values(state.assignments).some((item) => item.ticketId === ticket.id);
            const pendingInput = Object.values(state.inputs).some((input) => input.ticketId === ticket.id && !state.delivered.has(input.id));
            if (!neverAssigned && !pendingInput)
                continue;
            const assignment = {
                id: this.ids.next("as"),
                ticketId: ticket.id,
                state: "pending",
                executorRef: "",
                createdAt: now,
            };
            produced.push(ev.assignmentCreated(assignment, now));
            effects.enqueue(this.ids.next("eff"), "launch", { assignmentId: assignment.id }, now);
            capacity -= 1;
        }
        return this.store.appendAll(produced);
    }
    /** effects: launch —— 真正启动执行器。 */
    async launch(assignmentId) {
        const state = this.store.state();
        const assignment = state.assignments[assignmentId];
        if (!assignment)
            throw new Error(`unknown assignment ${assignmentId}`);
        const ticket = state.tickets[assignment.ticketId];
        if (!ticket)
            throw new Error(`unknown ticket ${assignment.ticketId}`);
        await this.executor.launch(assignment, ticket);
        return [ev.assignmentStarted(assignment.id, this.clock.now())];
    }
    /** effects: deliver —— 把输入投递给执行器。 */
    async deliver(inputId) {
        const state = this.store.state();
        const input = state.inputs[inputId];
        if (!input)
            throw new Error(`unknown input ${inputId}`);
        const ticket = state.tickets[input.ticketId];
        if (!ticket)
            throw new Error(`unknown ticket ${input.ticketId}`);
        await this.executor.deliver(ticket, input);
        return [ev.inputDelivered(input.id, this.clock.now())];
    }
    /** effects: send —— 通过信道把消息发出去。 */
    async send(messageId) {
        const message = this.store.state().messages[messageId];
        if (!message)
            throw new Error(`unknown message ${messageId}`);
        if (!this.channels)
            throw new Error("no channel writer configured");
        await this.channels.send({ id: message.channelId, threadId: "", address: message.address }, message.text);
        return [ev.messageSent(message.id, this.clock.now())];
    }
    /** 人的消息进入工单：结束的工单会被 resume（被 stop 的除外）。 */
    personMessage(ticketId, text, effects) {
        const now = this.clock.now();
        const ticket = this.store.state().tickets[ticketId];
        if (!ticket)
            throw new Error(`unknown ticket ${ticketId}`);
        const input = {
            id: this.ids.next("inp"),
            ticketId,
            kind: "text",
            ref: text.slice(0, 500),
            at: now,
        };
        const produced = [ev.inputFannedOut(input, now)];
        if (ticket.state === "ended" && !ticket.stopped)
            produced.push(ev.ticketResumed(ticketId, now));
        effects.enqueue(this.ids.next("eff"), "deliver", { inputId: input.id }, now);
        return this.store.appendAll(produced);
    }
    /** 执行器报告：结束 assignment；ready/dropped 直接结束工单。 */
    report(report) {
        const now = this.clock.now();
        const state = this.store.state();
        const assignment = state.assignments[report.assignmentId];
        // retry/stop 之后迟到的报告不能落库，否则会把已结束 assignment 重新算成完成。
        if (!assignment || assignment.state !== "running")
            return [];
        this.store.append(ev.reportRecorded(report, now));
        const produced = [];
        produced.push(ev.assignmentEnded(assignment.id, report.status, now));
        this.stopQuietly(assignment);
        if (report.status === "ready" || report.status === "dropped") {
            const ticket = state.tickets[report.ticketId];
            if (ticket && ticket.state === "open") {
                produced.push(ev.ticketEnded(ticket.id, report.status, report.summary, now));
            }
        }
        return produced.length > 0 ? this.store.appendAll(produced) : [];
    }
    /** 运维重试：结束当前 assignment，并投递一条 retry 输入让工单重新排到执行器。 */
    retry(ticketId, effects) {
        const now = this.clock.now();
        const state = this.store.state();
        if (!state.tickets[ticketId])
            throw new Error(`unknown ticket ${ticketId}`);
        const produced = [];
        for (const assignment of Object.values(state.assignments)) {
            if (assignment.ticketId === ticketId && assignment.state !== "ended") {
                produced.push(ev.assignmentEnded(assignment.id, "retry", now));
                this.stopQuietly(assignment);
            }
        }
        produced.push(this.makeInput(ticketId, "retry", "operator retry", effects, now));
        return this.store.appendAll(produced);
    }
    /** 进程重启恢复：收口所有 running assignment，并留下恢复注记。 */
    recoverAfterRestart(effects) {
        const now = this.clock.now();
        const state = this.store.state();
        const produced = [];
        const resumed = new Set();
        for (const assignment of Object.values(state.assignments)) {
            if (assignment.state !== "running")
                continue;
            produced.push(ev.assignmentEnded(assignment.id, "host-restarted", now));
            if (resumed.has(assignment.ticketId))
                continue;
            resumed.add(assignment.ticketId);
            produced.push(this.makeInput(assignment.ticketId, "resume", "host restarted; check directory, git and remote before repeating outside actions", effects, now));
        }
        return produced.length > 0 ? this.store.appendAll(produced) : [];
    }
    /** 维护者/看门狗在线改策略：只追加事件，Gate 立即按新版本判断。 */
    setPolicy(policy) {
        return this.store.appendAll([ev.policyChanged(policy, this.clock.now())]);
    }
    stopQuietly(assignment) {
        try {
            const result = this.executor.stop(assignment);
            if (result && typeof result.catch === "function") {
                void result.catch(() => undefined);
            }
        }
        catch {
            // 执行器已退出：忽略
        }
    }
    makeInput(ticketId, kind, ref, effects, now) {
        const input = {
            id: this.ids.next("inp"),
            ticketId,
            kind,
            ref,
            at: now,
        };
        effects.enqueue(this.ids.next("eff"), "deliver", { inputId: input.id }, now);
        return ev.inputFannedOut(input, now);
    }
}
//# sourceMappingURL=actions.js.map