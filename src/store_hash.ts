/** 快照规范化：回放确定性比较与哈希的唯一形状。 */

import type { State } from "./domain.ts";

export function canonicalState(state: State): string {
  const reports: Record<string, string[]> = {};
  for (const ticketId of Object.keys(state.reports).sort()) {
    reports[ticketId] = (state.reports[ticketId] ?? []).map((report) => report.status);
  }
  const assignments: Record<string, string> = {};
  for (const id of Object.keys(state.assignments).sort()) {
    assignments[id] = state.assignments[id]?.state ?? "";
  }
  const evals: Record<string, string> = {};
  for (const id of Object.keys(state.evals).sort()) {
    evals[id] = state.evals[id]?.state ?? "";
  }
  const summary = {
    triggers: Object.keys(state.triggers).sort(),
    threads: Object.keys(state.threads).sort(),
    tickets: Object.keys(state.tickets)
      .sort()
      .map((id) => {
        const ticket = state.tickets[id];
        return [id, ticket?.state, ticket?.stopped, ticket?.mandate.policyVersion];
      }),
    evals,
    assignments,
    subscriptions: state.subscriptions
      .map((item) => [item.ticketId, item.threadId, item.kind])
      .sort(),
    reports,
    inputs: Object.keys(state.inputs).sort(),
    attentions: Object.keys(state.attentions).sort(),
    dispositions: Object.keys(state.dispositions).sort(),
    undelivered: [...state.undelivered].sort(),
    delivered: [...state.delivered].sort(),
    policy: state.policy?.version ?? null,
  };
  return JSON.stringify(summary);
}