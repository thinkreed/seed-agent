/**
 * Router Session（文章 §2.1）：常驻、跨 Thread 批处理、带记忆与对话历史。
 *
 * - 常驻：memory 与 history 跨批次保留；
 * - 批处理：同一轮 tick 内多个 Thread 的 assess() 合并成一次模型调用；
 * - 可召回：模型可先返回 {"recall":[...]}，由 recall() 取回下一跳再决策；
 * - 对话：chat() 承接人类消息（面板/IM），而不是把每句话都变成工单。
 *
 * 该实现同时被内核 CLI 与 DSH host 复用（host 只做转发），避免同类逻辑两处维护。
 */
import { DEFAULT_BUDGET, buildView } from "./context.js";
import { SystemClock } from "./clock.js";
import { assessmentSystemPrompt, assessmentUserPrompt, routerSystemPrompt } from "./prompts.js";
import { recall } from "./recall.js";
import { decisionOf, ignored, parseChatResult, parsePayload, readDecisions, readRecalls, } from "./router_session_parse.js";
import { ROUTER_ACCEPT_RULES, ROUTER_CHAT_RULES, channelChatRules } from "./router_session_rules.js";
import { loadChatHistory, saveChatHistory } from "./router_session_history.js";
export { createRouterClient } from "./router_session_rules.js";
const ACCEPT_RULES = ROUTER_ACCEPT_RULES;
const CHAT_RULES = ROUTER_CHAT_RULES;
export class RouterSession {
    client;
    state;
    budget;
    maxSteps;
    historyMessages;
    memoryChars;
    clock;
    onBatch;
    historyPath;
    pending = [];
    history = [];
    memory = "";
    scheduled = false;
    lastBatch;
    constructor(options) {
        this.client = options.client;
        this.state = options.state;
        this.budget = options.budget ?? DEFAULT_BUDGET;
        this.maxSteps = options.maxSteps ?? 3;
        this.historyMessages = options.historyMessages ?? 20;
        this.memoryChars = options.memoryChars ?? 2000;
        this.clock = options.clock ?? new SystemClock();
        this.onBatch = options.onBatch;
        this.historyPath = options.historyPath;
        this.history.push(...loadChatHistory(this.historyPath));
    }
    /** 同一轮 tick 内的多个 Thread 请求在这里聚合。 */
    assess(context) {
        return new Promise((resolve) => {
            this.pending.push({ context, resolve });
            this.schedule();
        });
    }
    /** Router 观测所有进入系统的事件（含直通 Worker 的），只更新全局记忆，不参与路由。 */
    observe(trigger) {
        const where = trigger.threadIds[0] ?? "-";
        this.remember(`event ${trigger.source}/${where} from ${trigger.actor}: ${trigger.text.slice(0, 200)}`);
    }
    /** 人类消息进入 Router（面板/IM 对话）；channel 决定交互规范。 */
    async chat(text, channel = "im") {
        return (await this.chatResult(text, channel)).reply;
    }
    /** 对话结果；work 非空时调用方应创建工单。 */
    async chatResult(text, channel = "im") {
        const state = this.state();
        const tickets = Object.values(state.tickets)
            .sort((a, b) => a.id.localeCompare(b.id))
            .slice(-20)
            .map((ticket) => ({
            id: ticket.id,
            shortName: ticket.shortName,
            state: ticket.state,
            threadIds: ticket.threadIds,
            channelIds: ticket.channelIds,
        }));
        const messages = [
            {
                role: "system",
                content: `${routerSystemPrompt()}\n\n${CHAT_RULES}\n\n${channelChatRules(channel)}`,
            },
            ...this.history.slice(-this.historyMessages),
            { role: "user", content: JSON.stringify({ memory: this.memory || "(empty)", chat: text, tickets }) },
        ];
        const raw = await this.client.complete(messages);
        const result = parseChatResult(raw);
        this.remember(`person: ${text}\nrouter: ${result.reply}`);
        this.history.push({ role: "user", content: JSON.stringify({ chat: text }) });
        this.history.push({ role: "assistant", content: JSON.stringify({ reply: result.reply }) });
        this.trimHistory();
        saveChatHistory(this.historyPath, this.history);
        return result;
    }
    snapshot() {
        return { memory: this.memory, history: this.history.length, lastBatch: this.lastBatch };
    }
    schedule() {
        if (this.scheduled)
            return;
        this.scheduled = true;
        setImmediate(() => {
            void this.flush();
        });
    }
    async flush() {
        this.scheduled = false;
        const batch = this.pending.splice(0);
        if (batch.length === 0)
            return;
        const views = batch.map((item) => buildView(item.context, this.budget));
        const info = {
            threads: views.length,
            triggers: views.reduce((total, view) => total + view.triggers.length, 0),
            at: Math.floor(this.clock.now()),
        };
        this.lastBatch = info;
        this.onBatch?.(info);
        let decisions;
        try {
            decisions = await this.decide(views);
        }
        catch (error) {
            const reason = String(error).slice(0, 200);
            this.remember(`decision-error: ${reason}`);
            decisions = new Map(views.map((view) => [view.threadId, ignored(reason)]));
        }
        for (const item of batch) {
            item.resolve(decisions.get(item.context.threadId) ?? ignored("router-no-decision"));
        }
        this.remember(`batch threads=${info.threads} triggers=${info.triggers} → ` +
            [...decisions.entries()].map(([threadId, decision]) => `${threadId}:${decision.kind}`).join(","));
    }
    async decide(views) {
        const messages = [
            {
                role: "system",
                content: `${routerSystemPrompt()}\n\n${ACCEPT_RULES}`,
            },
            ...this.history.slice(-this.historyMessages),
            {
                role: "user",
                content: JSON.stringify({
                    memory: this.memory || "(empty)",
                    threads: views.map((view) => ({
                        view,
                        assessment: assessmentSystemPrompt(),
                        context: assessmentUserPrompt(view),
                    })),
                }),
            },
        ];
        for (let step = 0; step < this.maxSteps; step += 1) {
            const raw = await this.client.complete(messages);
            const payload = parsePayload(raw);
            if (!payload)
                return new Map(views.map((view) => [view.threadId, ignored("router-unparsable")]));
            const recalls = readRecalls(payload);
            if (recalls.length > 0) {
                const results = recalls.map((request) => recall(this.state(), request.kind, request.id, this.budget));
                messages.push({ role: "assistant", content: raw });
                messages.push({ role: "user", content: JSON.stringify({ recallResults: results }) });
                continue;
            }
            const decisions = readDecisions(payload);
            if (decisions.size > 0)
                return decisions;
            if (typeof payload.kind === "string") {
                const single = decisionOf(payload);
                return new Map(views.map((view) => [view.threadId, single]));
            }
            return new Map(views.map((view) => [view.threadId, ignored("router-empty")]));
        }
        return new Map(views.map((view) => [view.threadId, ignored("router-step-limit")]));
    }
    remember(line) {
        const next = `${this.memory}\n${line}`.trim();
        this.memory = next.length > this.memoryChars ? next.slice(-this.memoryChars) : next;
    }
    trimHistory() {
        const limit = this.historyMessages;
        if (this.history.length > limit * 2)
            this.history.splice(0, this.history.length - limit * 2);
    }
}
//# sourceMappingURL=router_session.js.map