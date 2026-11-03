/** 快照规范化：回放确定性比较与哈希的唯一形状。 */
import type { State } from "./domain.ts";
export declare function canonicalState(state: State): string;
