/** Watchdog 的模型裁定：把确定性 findings 交给模型判断是否需要介入。 */

import { extractJsonObject } from "./json.ts";
import type { WatchdogFinding, WatchdogJudge, WatchdogVerdict } from "./watchdog.ts";
import type { State } from "./domain.ts";
import type { ModelClient } from "./model.ts";
import { watchdogSystemPrompt, watchdogUserPrompt } from "./prompts.ts";

export class LlmWatchdogJudge implements WatchdogJudge {
  private readonly client: ModelClient;
  private readonly maxFindings: number;

  constructor(client: ModelClient, maxFindings = 20) {
    this.client = client;
    this.maxFindings = maxFindings;
  }

  async judge(findings: readonly WatchdogFinding[], state: State): Promise<WatchdogVerdict> {
    const sample = findings.slice(0, this.maxFindings);
    const context = {
      findings: sample,
      openTickets: Object.values(state.tickets)
        .filter((ticket) => ticket.state === "open")
        .map((ticket) => ({ id: ticket.id, shortName: ticket.shortName })),
    };
    const raw = await this.client.complete([
      { role: "system", content: watchdogSystemPrompt() },
      { role: "user", content: watchdogUserPrompt(context) },
    ]);
    const parsed = extractJsonObject(raw);
    const action = parsed?.action === "intervene" ? "intervene" : "ok";
    const reason = typeof parsed?.reason === "string" ? parsed.reason.slice(0, 300) : "model-judged";
    return { action, reason };
  }
}