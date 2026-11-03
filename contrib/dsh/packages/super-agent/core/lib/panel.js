/** 面板：只读快照展示，只回答"谁在等我"。 */
import { ticketReport } from "./domain.js";
import { requiresPerson, stageOf } from "./fsm.js";
/** 先列需要人的，再列在跑的；健康空闲的工单不占空间。 */
export function rows(state) {
    const collected = [];
    for (const ticket of Object.values(state.tickets).sort((a, b) => a.id.localeCompare(b.id))) {
        const stage = stageOf(state, ticket);
        if (stage === "idle")
            continue;
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
export function render(state) {
    const lines = ["SHORT    STAGE              SUMMARY"];
    for (const row of rows(state)) {
        lines.push(`${row.shortName.padEnd(8)} ${row.stage.padEnd(18)} ${row.summary}`);
    }
    if (lines.length === 1)
        lines.push("(nothing waits for a person)");
    return lines.join("\n");
}
/** 机器可读输出：CI/脚本用。 */
export function renderJson(state) {
    return JSON.stringify(rows(state).map((row) => ({
        ticketId: row.ticketId,
        shortName: row.shortName,
        stage: row.stage,
        waitingPerson: row.waitingPerson,
        summary: row.summary,
    })), null, 2);
}
//# sourceMappingURL=panel.js.map