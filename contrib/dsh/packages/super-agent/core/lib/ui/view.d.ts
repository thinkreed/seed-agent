/** 界面视图模型：把只读 State 投影成桌面端需要的 DTO（纯函数，便于测试）。 */
import type { State } from "../domain.ts";
export interface UiTicket {
    readonly id: string;
    readonly shortName: string;
    readonly state: string;
    readonly stage: string;
    readonly waitingPerson: boolean;
    readonly source: string;
    readonly actor: string;
    readonly title: string;
    readonly summary: string;
    readonly updatedAt: number;
}
export interface UiState {
    readonly paused: boolean;
    readonly slots: number;
    readonly lastSeq: number;
    readonly counts: {
        readonly total: number;
        readonly open: number;
        readonly ended: number;
        readonly waitingPerson: number;
    };
    readonly tickets: readonly UiTicket[];
}
export interface TimelineItem {
    readonly kind: "trigger" | "input" | "report" | "message";
    readonly at: number;
    readonly who: string;
    readonly text: string;
    readonly status?: string;
}
export interface UiTicketView {
    readonly ticket: UiTicket;
    readonly mandate: {
        readonly source: string;
        readonly actor: string;
        readonly scope: string;
        readonly strength: string;
        readonly policyVersion: string;
    };
    readonly timeline: readonly TimelineItem[];
}
export declare function buildUiState(state: State, meta: {
    paused: boolean;
    slots: number;
    lastSeq: number;
}): UiState;
export declare function buildTicketView(state: State, ticketId: string): UiTicketView | null;
/** 事件流一行：只保留可读摘要，避免把整个 payload 抛给界面。 */
export declare function eventRow(event: {
    seq: number;
    type: string;
    at: number;
}): {
    seq: number;
    type: string;
    at: number;
};
