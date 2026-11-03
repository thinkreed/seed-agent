/** 真实评估器：组装 Inline & Spill 上下文 + 提示词，调用模型并解析决定。 */
import { parseDecision } from "./assessor.js";
import { buildView, DEFAULT_BUDGET } from "./context.js";
import { assessmentSystemPrompt, assessmentUserPrompt } from "./prompts.js";
export class LlmAssessor {
    client;
    budget;
    constructor(client, budget = DEFAULT_BUDGET) {
        this.client = client;
        this.budget = budget;
    }
    async assess(context) {
        const view = buildView(context, this.budget);
        const messages = [
            { role: "system", content: assessmentSystemPrompt() },
            { role: "user", content: assessmentUserPrompt(view) },
        ];
        const raw = await this.client.complete(messages);
        return parseDecision(raw);
    }
}
//# sourceMappingURL=assessor_llm.js.map