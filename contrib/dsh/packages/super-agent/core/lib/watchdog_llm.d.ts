/** Watchdog 的模型裁定：把确定性 findings 交给模型判断是否需要介入。 */
import type { WatchdogAdvisor, WatchdogFinding, WatchdogJudge, WatchdogVerdict } from "./watchdog.ts";
import type { State } from "./domain.ts";
import type { ModelClient } from "./model.ts";
export declare class LlmWatchdogJudge implements WatchdogJudge {
    private readonly client;
    private readonly maxFindings;
    constructor(client: ModelClient, maxFindings?: number);
    judge(findings: readonly WatchdogFinding[], state: State): Promise<WatchdogVerdict>;
}
/** 自然语言运维问答：同一个外部控制回路，回答"为什么卡住/该做什么"。 */
export declare class LlmWatchdogAdvisor implements WatchdogAdvisor {
    private readonly client;
    constructor(client: ModelClient);
    answer(question: string, state: State): Promise<string>;
}
