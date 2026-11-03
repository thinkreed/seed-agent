/** 评估器装配：默认常驻 Router Session（文章 §2.1），可配置退回单次评估器。 */
import type { SeedConfig } from "./config_types.ts";
import type { State } from "./domain.ts";
import type { ModelClient } from "./model.ts";
import type { Assessor } from "./ports.ts";
import { RouterSession } from "./router_session.ts";
export interface AssessorBundle {
    readonly assessor: Assessor;
    /** routerMode=llm 时可用于人类对话（面板/CLI chat）。 */
    readonly router?: RouterSession;
}
export declare function buildAssessor(config: SeedConfig, modelClient: ModelClient, state: () => State): AssessorBundle;
