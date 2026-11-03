/** 面板：只读快照展示，只回答"谁在等我"。 */
import type { Stage, State } from "./domain.ts";
export interface PanelRow {
    readonly ticketId: string;
    readonly shortName: string;
    readonly stage: Stage;
    readonly waitingPerson: boolean;
    readonly summary: string;
}
/** 先列需要人的，再列在跑的；健康空闲的工单不占空间。 */
export declare function rows(state: State): PanelRow[];
export declare function render(state: State): string;
/** 机器可读输出：CI/脚本用。 */
export declare function renderJson(state: State): string;
