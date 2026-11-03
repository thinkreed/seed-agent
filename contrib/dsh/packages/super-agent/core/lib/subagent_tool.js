/**
 * Worker 内部的 Subagent 工具（文章 §2.2：Worker 可再创建 Subagent 执行子任务）。
 *
 * 子任务跑在独立上下文里，但共享模型、工具与后台任务注册表；
 * 递归 spawn 被过滤，避免无限套娃。返回结构化报告，由父 Worker 决定如何汇报。
 */
import { ReactLoop } from "./react.js";
export function subagentTool(options) {
    let counter = 0;
    return {
        description: "Run a focused subtask in an isolated subagent context. " +
            'Args: {"task":"..."}; returns {status, summary}. Prefer it for independent checks.',
        run: async (args) => {
            const task = typeof args.task === "string" ? args.task.trim() : "";
            if (!task)
                return { error: "task required" };
            const nestedTools = Object.fromEntries(Object.entries(options.tools).filter(([name]) => name !== "spawn_subagent"));
            const loop = new ReactLoop({
                model: options.model,
                tools: nestedTools,
                jobs: options.jobs,
                clock: options.clock,
                maxSteps: options.maxSteps ?? 6,
            });
            counter += 1;
            const trigger = {
                id: `sub-${options.clock.now()}-${counter}`,
                source: "subagent",
                actor: "worker",
                text: task,
                threadIds: [],
                channelIds: [],
                at: options.clock.now(),
            };
            const report = await loop.run(options.ticket, [trigger]);
            return { status: report.status, summary: report.summary };
        },
    };
}
//# sourceMappingURL=subagent_tool.js.map