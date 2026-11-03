/**
 * Router：面向人的那一层。
 * 只做两件事：把"需要人看/需要人决定"的结果变成一条短消息，并交给信道发出去。
 */
import { ev } from "./builders.js";
import { ticketReport } from "./domain.js";
import { formatForChannel } from "./format.js";
import { stageOf } from "./fsm.js";
const NOTIFY_STATUSES = new Set(["ready", "blocked", "failed"]);
export class TemplateComposer {
    compose(_ticket, report, stage) {
        const summary = report.summary || "（无补充说明）";
        if (report.status === "ready")
            return `已完成：${summary}。请验收。`;
        if (report.status === "blocked")
            return `需要你决定：${summary}`;
        if (report.status === "failed")
            return `执行失败：${summary}`;
        return `进展：${summary}（${stage}）`;
    }
}
export class Router {
    store;
    clock;
    effects;
    composer;
    constructor(options) {
        this.store = options.store;
        this.clock = options.clock;
        this.effects = options.effects;
        this.composer = options.composer ?? new TemplateComposer();
    }
    /** 为"需要人"的结果排队一条消息；同一条报告只通知一次。 */
    queueReplies() {
        const state = this.store.state();
        const produced = [];
        for (const ticket of Object.values(state.tickets).sort((a, b) => a.id.localeCompare(b.id))) {
            if (ticket.stopped)
                continue;
            const address = ticket.channelIds[0];
            if (!address)
                continue;
            // 即时确认：工单刚受理、还没有任何报告时，先回一条“已在处理”。
            const ackId = `ack:${ticket.id}`;
            if (!state.messages[ackId] && !ticketReport(state, ticket.id)) {
                const ack = {
                    id: ackId,
                    ticketId: ticket.id,
                    channelId: address,
                    address,
                    text: formatForChannel(address, `已收到，正在处理：${ticket.title || ticket.shortName}。完成后回报。`),
                    at: this.clock.now(),
                };
                produced.push(ev.messageQueued(ack, this.clock.now()));
                this.effects.enqueue(`eff:${ackId}`, "send", { messageId: ackId }, this.clock.now());
            }
            const report = ticketReport(state, ticket.id);
            if (!report || !NOTIFY_STATUSES.has(report.status))
                continue;
            const messageId = `msg:${ticket.id}:${report.at}`;
            if (state.messages[messageId])
                continue;
            const message = {
                id: messageId,
                ticketId: ticket.id,
                channelId: address,
                address,
                text: formatForChannel(address, this.composer.compose(ticket, report, stageOf(state, ticket))),
                at: this.clock.now(),
            };
            produced.push(ev.messageQueued(message, this.clock.now()));
            this.effects.enqueue(`eff:${messageId}`, "send", { messageId }, this.clock.now());
        }
        return produced.length > 0 ? this.store.appendAll(produced) : [];
    }
}
//# sourceMappingURL=router.js.map