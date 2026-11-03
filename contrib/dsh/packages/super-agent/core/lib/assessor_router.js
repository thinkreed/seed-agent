/** 评估器装配：默认常驻 Router Session（文章 §2.1），可配置退回单次评估器。 */
import { LlmAssessor } from "./assessor_llm.js";
import { RouterSession } from "./router_session.js";
export function buildAssessor(config, modelClient, state) {
    if (config.routerMode === "off")
        return { assessor: new LlmAssessor(modelClient) };
    const router = new RouterSession({
        client: modelClient,
        state,
        historyPath: `${config.dbPath}.router-chat.json`,
    });
    return { assessor: router, router };
}
//# sourceMappingURL=assessor_router.js.map