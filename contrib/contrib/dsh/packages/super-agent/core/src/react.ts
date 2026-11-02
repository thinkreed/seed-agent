/**
 * 异步 ReAct 循环：耗时的工具走 start()/stop()，前台不必等待。
 *
 * 模型每一步只回一个 JSON 动作：
 *   {"action":"tool","tool":"read_file","args":{...}}
 *   {"action":"start","tool":"run_tests","args":{...}}
 *   {"action":"stop","jobId":"job-000001"}
 *   {"action":"report","status":"ready","summary":"..."}
 */

import type { Clock } from "./clock.ts";
import type { Report, ReportStatus, Ticket, Trigger } from "./domain.ts";
import { extractJsonObject } from "./json.ts";
import type { JobNotice, JobRegistry } from "./jobs.ts";
import type { ModelClient, ModelMessage } from "./model.ts";
import { workerSystemPrompt } from "./prompts.ts";

const STATUSES: ReadonlySet<string> = new Set([
  "progress",
  "waiting",
  "ready",
  "blocked",
  "failed",
  "dropped",
]);

export interface ReactTool {
  readonly description?: string;
  run(args: Record<string, unknown>, signal: AbortSignal): Promise<unknown>;
}

export interface ReactOptions {
  readonly model: ModelClient;
  readonly tools: Readonly<Record<string, ReactTool>>;
  readonly jobs: JobRegistry;
  readonly clock: Clock;
  readonly maxSteps?: number;
  readonly report?: (report: Report) => void;
  /** 全双工：每个推理步开始前取出当前到达的新输入（文章 §4.1）。 */
  readonly nextInputs?: () => string[];
}

type Action =
  | { action: "tool"; tool: string; args: Record<string, unknown> }
  | { action: "start"; tool: string; args: Record<string, unknown> }
  | { action: "stop"; jobId: string }
  | { action: "report"; status: ReportStatus; summary: string };

export class ReactLoop {
  private readonly options: ReactOptions;
  private readonly maxSteps: number;

  constructor(options: ReactOptions) {
    this.options = options;
    this.maxSteps = options.maxSteps ?? 8;
  }

  async run(ticket: Ticket, inputs: readonly Trigger[], signal?: AbortSignal): Promise<Report> {
    const toolList = Object.entries(this.options.tools).map(([name, tool]) => ({
      name,
      description: tool.description ?? "",
    }));
    const messages: ModelMessage[] = [
      { role: "system", content: workerSystemPrompt(ticket, inputs, toolList) },
      { role: "user", content: "Begin. Reply with exactly one JSON action." },
    ];

    for (let step = 0; step < this.maxSteps; step += 1) {
      if (signal?.aborted) return this.finish(ticket, "dropped", "aborted");
      this.injectJobNotices(messages);
      this.injectNewInputs(messages);
      const raw = await this.options.model.complete(messages);
      messages.push({ role: "assistant", content: raw });
      const action = parseAction(raw);
      if (!action) {
        messages.push({
          role: "user",
          content:
            "Your reply was not a valid action. Reply with exactly one JSON object: " +
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

  private injectJobNotices(messages: ModelMessage[]): void {
    for (const notice of this.options.jobs.drainNotices()) {
      messages.push({ role: "user", content: `job update: ${JSON.stringify(notice)}` });
    }
  }

  /** 回合进行中的新输入在下一个推理步开始前注入，不必等整个回合结束。 */
  private injectNewInputs(messages: ModelMessage[]): void {
    for (const text of this.options.nextInputs?.() ?? []) {
      messages.push({ role: "user", content: `new input: ${text}` });
    }
  }

  private async observe(
    ticket: Ticket,
    action: Exclude<Action, { action: "report" }>,
    signal?: AbortSignal,
  ): Promise<string> {
    if (action.action === "stop") {
      const stopped = this.options.jobs.stop(action.jobId);
      return `observation: ${JSON.stringify({ stopped: action.jobId, ok: stopped })}`;
    }
    const tool = this.options.tools[action.tool];
    if (!tool) return `observation: unknown tool ${action.tool}`;
    if (action.action === "start") {
      const jobId = this.options.jobs.start(
        action.tool,
        ticket.id,
        (jobSignal) =>
          tool.run(action.args, signal ? AbortSignal.any([signal, jobSignal]) : jobSignal),
      );
      return `observation: ${JSON.stringify({ started: jobId, tool: action.tool })}`;
    }
    try {
      const result = await tool.run(action.args, signal ?? new AbortController().signal);
      return `observation: ${JSON.stringify(result)}`;
    } catch (error) {
      return `observation: ${JSON.stringify({ error: String(error) })}`;
    }
  }

  private finish(ticket: Ticket, status: ReportStatus, summary: string): Report {
    const report: Report = { ticketId: ticket.id, assignmentId: "", status, summary, at: this.options.clock.now() };
    this.options.report?.(report);
    return report;
  }
}

export function parseAction(raw: string): Action | null {
  const payload = extractJsonObject(raw);
  if (!payload || typeof payload.action !== "string") return null;
  if (payload.action === "report") {
    const status = typeof payload.status === "string" ? payload.status : "";
    if (!STATUSES.has(status)) return null;
    return {
      action: "report",
      status: status as ReportStatus,
      summary: typeof payload.summary === "string" ? payload.summary.slice(0, 2000) : "",
    };
  }
  if (payload.action === "tool" || payload.action === "start") {
    if (typeof payload.tool !== "string" || !payload.tool) return null;
    const args =
      payload.args && typeof payload.args === "object" && !Array.isArray(payload.args)
        ? (payload.args as Record<string, unknown>)
        : {};
    return { action: payload.action, tool: payload.tool, args };
  }
  if (payload.action === "stop") {
    return typeof payload.jobId === "string" && payload.jobId ? { action: "stop", jobId: payload.jobId } : null;
  }
  return null;
}

export type { JobNotice };