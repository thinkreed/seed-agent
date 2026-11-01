/** 真实评估器：组装 Inline & Spill 上下文 + 提示词，调用模型并解析决定。 */

import { parseDecision } from "./assessor.ts";
import type { ContextBudget } from "./context.ts";
import { buildView, DEFAULT_BUDGET } from "./context.ts";
import type { Decision } from "./domain.ts";
import type { ModelClient, ModelMessage } from "./model.ts";
import type { AssessContext, Assessor } from "./ports.ts";
import { assessmentSystemPrompt, assessmentUserPrompt } from "./prompts.ts";

export class LlmAssessor implements Assessor {
  private readonly client: ModelClient;
  private readonly budget: ContextBudget;

  constructor(client: ModelClient, budget: ContextBudget = DEFAULT_BUDGET) {
    this.client = client;
    this.budget = budget;
  }

  async assess(context: AssessContext): Promise<Decision> {
    const view = buildView(context, this.budget);
    const messages: ModelMessage[] = [
      { role: "system", content: assessmentSystemPrompt() },
      { role: "user", content: assessmentUserPrompt(view) },
    ];
    const raw = await this.client.complete(messages);
    return parseDecision(raw);
  }
}