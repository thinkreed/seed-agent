/** 状态里已出现过的所有 ID（给 SeqIds 预热用）。 */

import type { State } from "./domain.ts";

export function stateIds(state: State): string[] {
  const ids: string[] = [];
  for (const group of [
    state.triggers,
    state.threads,
    state.tickets,
    state.evals,
    state.assignments,
    state.inputs,
    state.attentions,
    state.messages,
    state.dispositions,
  ]) {
    ids.push(...Object.keys(group));
  }
  return ids;
}