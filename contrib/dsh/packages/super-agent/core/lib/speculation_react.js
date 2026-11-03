/**
 * 内核版投机执行器：用真实 ReactLoop 在独立目录里静默尝试。
 * 只有模型明确 report ready（确认问题且找到简单修复）才判定为可交付。
 */
import { JobRegistry } from "./jobs.js";
import { ReactLoop } from "./react.js";
import { fileTools } from "./tools/files.js";
import { shellTool } from "./tools/shell.js";
export function reactSpeculationRunner(options) {
    const jobs = options.jobs ?? new JobRegistry(options.clock, { maxRunSeconds: 600 });
    const tools = {
        ...fileTools(options.root),
        run_shell: shellTool({ root: options.root }),
    };
    return {
        async run(candidate, signal) {
            const instruction = [
                "你在做一次静默的投机尝试（用户看不到，只有值得交付才会上报）。",
                "目标：确认问题是否真实存在，并尝试一个简单、可验证的修复。",
                "如果确认问题且修复简单：report status=ready，summary 写可交付结论。",
                "否则 report status=blocked 或 dropped，summary 说明为何不值得交付。",
                "",
                candidate.text,
            ].join("\n");
            const trigger = {
                id: `spec:${candidate.id}`,
                source: "speculation",
                actor: "speculator",
                text: instruction,
                threadIds: candidate.threadIds ?? [],
                channelIds: candidate.channelIds,
                at: options.clock.now(),
            };
            const loop = new ReactLoop({
                model: options.model,
                tools,
                jobs,
                clock: options.clock,
                maxSteps: options.maxSteps ?? 6,
            });
            const report = await loop.run(options.ticket, [trigger], signal);
            return {
                deliver: report.status === "ready",
                summary: report.summary || report.status,
            };
        },
    };
}
//# sourceMappingURL=speculation_react.js.map