/**
 * 异步 ReAct 循环：耗时的工具走 start()/stop()，前台不必等待。
 *
 * 模型每一步只回一个 JSON 动作：
 *   {"action":"tool","tool":"read_file","args":{...}}
 *   {"action":"start","tool":"run_tests","args":{...}}
 *   {"action":"stop","jobId":"job-000001"}
 *   {"action":"report","status":"ready","summary":"..."}
 */
import { extractJsonObject } from "./json.js";
import { workerSystemPrompt } from "./prompts.js";
const STATUSES = new Set([
    "progress",
    "waiting",
    "ready",
    "blocked",
    "failed",
    "dropped",
]);
export class ReactLoop {
    options;
    maxSteps;
    constructor(options) {
        this.options = options;
        this.maxSteps = options.maxSteps ?? 8;
    }
    async run(ticket, inputs, signal) {
        const toolList = Object.entries(this.options.tools).map(([name, tool]) => ({
            name,
            description: tool.description ?? "",
        }));
        const messages = [
            { role: "system", content: workerSystemPrompt(ticket, inputs, toolList) },
            { role: "user", content: "Begin. Reply with exactly one JSON action." },
        ];
        for (let step = 0; step < this.maxSteps; step += 1) {
            if (signal?.aborted)
                return this.finish(ticket, "dropped", "aborted");
            this.injectJobNotices(messages);
            this.injectNewInputs(messages);
            const raw = await this.options.model.complete(messages);
            messages.push({ role: "assistant", content: raw });
            const action = parseAction(raw);
            if (!action) {
                messages.push({
                    role: "user",
                    content: "Your reply was not a valid action. Reply with exactly one JSON object: " +
                        '{"action":"tool","tool":"...","args":{}} or {"action":"report","status":"...","summary":"..."}',
                });
                continue;
            }
            if (action.action === "report") {
                return this.finish(ticket, action.status, action.summary);
            }
            messages.push({ role: "user", content: await this.observe(ticket, action, signal) });
        }
        return this.finish(ticket, "failed", `max steps (${this.maxSteps}) reached`);
    }
    injectJobNotices(messages) {
        for (const notice of this.options.jobs.drainNotices()) {
            messages.push({ role: "user", content: `job update: ${JSON.stringify(notice)}` });
        }
    }
    /** 回合进行中的新输入在下一个推理步开始前注入，不必等整个回合结束。 */
    injectNewInputs(messages) {
        for (const text of this.options.nextInputs?.() ?? []) {
            messages.push({ role: "user", content: `new input: ${text}` });
        }
    }
    async observe(ticket, action, signal) {
        if (action.action === "stop") {
            const stopped = this.options.jobs.stop(action.jobId);
            return `observation: ${JSON.stringify({ stopped: action.jobId, ok: stopped })}`;
        }
        const tool = this.options.tools[action.tool];
        if (!tool)
            return `observation: unknown tool ${action.tool}`;
        if (action.action === "start") {
            const jobId = this.options.jobs.start(action.tool, ticket.id, (jobSignal) => tool.run(action.args, signal ? AbortSignal.any([signal, jobSignal]) : jobSignal));
            return `observation: ${JSON.stringify({ started: jobId, tool: action.tool })}`;
        }
        try {
            const result = await tool.run(action.args, signal ?? new AbortController().signal);
            return `observation: ${JSON.stringify(result)}`;
        }
        catch (error) {
            return `observation: ${JSON.stringify({ error: String(error) })}`;
        }
    }
    finish(ticket, status, summary) {
        const report = { ticketId: ticket.id, assignmentId: "", status, summary, at: this.options.clock.now() };
        this.options.report?.(report);
        return report;
    }
}
export function parseAction(raw) {
    const payload = extractJsonObject(raw);
    if (!payload || typeof payload.action !== "string")
        return null;
    if (payload.action === "report") {
        const status = typeof payload.status === "string" ? payload.status : "";
        if (!STATUSES.has(status))
            return null;
        return {
            action: "report",
            status: status,
            summary: typeof payload.summary === "string" ? payload.summary.slice(0, 2000) : "",
        };
    }
    if (payload.action === "tool" || payload.action === "start") {
        if (typeof payload.tool !== "string" || !payload.tool)
            return null;
        const args = payload.args && typeof payload.args === "object" && !Array.isArray(payload.args)
            ? payload.args
            : {};
        return { action: payload.action, tool: payload.tool, args };
    }
    if (payload.action === "stop") {
        return typeof payload.jobId === "string" && payload.jobId ? { action: "stop", jobId: payload.jobId } : null;
    }
    return null;
}
//# sourceMappingURL=react.js.map