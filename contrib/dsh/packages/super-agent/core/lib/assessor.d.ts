/** 模型决策解析：把模型输出解析成 Decision，解析失败一律降级为 ignore。 */
import type { Decision } from "./domain.ts";
export declare function parseDecision(raw: string): Decision;
