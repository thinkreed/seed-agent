/** 状态里已出现过的所有 ID（给 SeqIds 预热用）。 */
import type { State } from "./domain.ts";
export declare function stateIds(state: State): string[];
