/** 面板：只读快照展示，只回答"谁在等我"。 */

import type { Stage, State } from "./domain.ts";
import { ticketReport } from "./domain.ts";
import { requiresPerson, stageOf } from "./fsm.ts";

export interface PanelRow {
  readonly ticketId: string;
  readonly shortName: string;
  readonly stage: Stage;
  readonly waitingPerson: boolean;
  readonly summary: string;
}

/** 先列需要人的，再列在跑的；健康空闲的工单不占空间。 */
export function rows(state: State): PanelRow[] {
  const collected: PanelRow[] = [];
  for (const ticket of Object.values(state.tickets).sort((a, b) => a.id.localeCompare(b.id))) {
    const stage = stageOf(state, ticket);
    if (stage === "idle") continue;
    const report = ticketReport(state, ticket.id);
    collected.push({
      ticketId: ticket.id,
      shortName: ticket.shortName,
      stage,
      waitingPerson: requiresPerson(stage),
      summary: report?.summary ?? "",
    });
  }
  collected.sort((a, b) => Number(b.waitingPerson) - Number(a.waitingPerson));
  return collected;
}

export function render(state: State): string {
  const lines = ["SHORT    STAGE              SUMMARY"];
  for (const row of rows(state)) {
    lines.push(`${row.shortName.padEnd(8)} ${row.stage.padEnd(18)} ${row.summary}`);
  }
  if (lines.length === 1) lines.push("(nothing waits for a person)");
  return lines.join("\n");
}