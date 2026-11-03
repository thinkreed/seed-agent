/** 真实评估器：组装 Inline & Spill 上下文 + 提示词，调用模型并解析决定。 */
import type { ContextBudget } from "./context.ts";
import type { Decision } from "./domain.ts";
import type { ModelClient } from "./model.ts";
import type { AssessContext, Assessor } from "./ports.ts";
export declare class LlmAssessor implements Assessor {
    private readonly client;
    private readonly budget;
    constructor(client: ModelClient, budget?: ContextBudget);
    assess(context: AssessContext): Promise<Decision>;
}
