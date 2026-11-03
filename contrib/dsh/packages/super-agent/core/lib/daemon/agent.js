/**
 * DaemonAgent：执行环境侧。收到指令 -> 用本地执行器干活 -> 把报告作为事件推回去。
 * 自己不持有会话状态（无状态可随时重启），状态都在计算侧的 Store。
 */
import { LocalExecutor } from "../executor/local.js";
export class DaemonAgent {
    options;
    workers = new Map();
    constructor(options) {
        this.options = options;
    }
    async handle(request) {
        try {
            if (request.cmd === "launch")
                return await this.launch(request);
            if (request.cmd === "deliver")
                return await this.deliver(request);
            return await this.stop(request);
        }
        catch (error) {
            return { id: request.id, ok: false, error: String(error) };
        }
    }
    async launch(request) {
        // 设备重连后会重发 launch：先收口同工单的旧执行器，避免重复占用。
        const existing = this.workers.get(request.ticketId);
        if (existing)
            await existing.executor.stop(existing.assignment);
        const clock = this.options.clock;
        const ticket = {
            id: request.ticketId,
            shortName: request.shortName,
            mandate: {
                policyVersion: "",
                strength: "explicit",
                scope: request.scope,
                source: "daemon",
                actor: "",
                rules: [],
                triggerId: "",
            },
            threadIds: [],
            channelIds: [],
            state: "open",
            stopped: false,
            createdAt: clock.now(),
        };
        const assignment = {
            id: request.assignmentId,
            ticketId: request.ticketId,
            state: "running",
            executorRef: "local-daemon",
            createdAt: clock.now(),
        };
        const executor = new LocalExecutor({
            root: this.options.root,
            worker: request.worker,
            ...(request.prepare ? { prepare: request.prepare } : {}),
            clock,
            ...(this.options.env ? { env: this.options.env } : {}),
            report: (report) => {
                this.options.emit({
                    type: "report",
                    ticketId: report.ticketId,
                    assignmentId: report.assignmentId,
                    status: report.status,
                    summary: report.summary,
                    at: report.at,
                });
            },
        });
        await executor.launch(assignment, ticket);
        this.workers.set(request.ticketId, { assignment, ticket, executor });
        return { id: request.id, ok: true };
    }
    async deliver(request) {
        const worker = this.workers.get(request.ticketId);
        if (!worker)
            throw new Error(`no worker for ticket ${request.ticketId}`);
        const input = {
            id: request.inputId,
            ticketId: request.ticketId,
            kind: request.kind,
            ref: request.ref,
            at: this.options.clock.now(),
        };
        await worker.executor.deliver(worker.ticket, input);
        return { id: request.id, ok: true };
    }
    async stop(request) {
        const worker = this.workers.get(request.ticketId);
        if (worker) {
            await worker.executor.stop(worker.assignment);
            this.workers.delete(request.ticketId);
        }
        return { id: request.id, ok: true };
    }
    /** daemon 启动时调用：报告自己在哪些工单上还活着（用于重连恢复）。 */
    liveTickets() {
        return [...this.workers.keys()];
    }
}
//# sourceMappingURL=agent.js.map