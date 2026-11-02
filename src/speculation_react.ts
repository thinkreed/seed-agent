/**
 * 内核版投机执行器：用真实 ReactLoop 在独立目录里静默尝试。
 * 只有模型明确 report ready（确认问题且找到简单修复）才判定为可交付。
 */

import type { Clock } from "./clock.ts";
import type { Ticket, Trigger } from "./domain.ts";
import { JobRegistry } from "./jobs.ts";
import type { ModelClient } from "./model.ts";
import { ReactLoop } from "./react.ts";
import type { SpeculationCandidate, SpeculationRunner, SpeculationVerdict } from "./speculation.ts";
import { fileTools } from "./tools/files.ts";
import { shellTool } from "./tools/shell.ts";

export interface ReactSpeculationOptions {
  readonly model: ModelClient;
  readonly root: string;
  readonly clock: Clock;
  readonly ticket: Ticket;
  readonly jobs?: JobRegistry;
  readonly maxSteps?: number;
}

export function reactSpeculationRunner(options: ReactSpeculationOptions): SpeculationRunner {
  const jobs = options.jobs ?? new JobRegistry(options.clock, { maxRunSeconds: 600 });
  const tools = {
    ...fileTools(options.root),
    run_shell: shellTool({ root: options.root }),
  };
  return {
    async run(candidate: SpeculationCandidate, signal: AbortSignal): Promise<SpeculationVerdict> {
      const instruction = [
        "你在做一次静默的投机尝试（用户看不到，只有值得交付才会上报）。",
        "目标：确认问题是否真实存在，并尝试一个简单、可验证的修复。",
        "如果确认问题且修复简单：report status=ready，summary 写可交付结论。",
        "否则 report status=blocked 或 dropped，summary 说明为何不值得交付。",
        "",
        candidate.text,
      ].join("\n");
      const trigger: Trigger = {
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