/** 内核 Worker 的链式召回索引：把事件/线程/工单投影成可逐跳读取的 JSON。 */
import type { State } from "./domain.ts";
export interface RecallIndex {
    readonly generatedAt: number;
    readonly triggers: Record<string, unknown>;
    readonly threads: Record<string, unknown>;
    readonly tickets: Record<string, unknown>;
}
export declare function buildRecallIndex(state: State, now: number): RecallIndex;
export declare function writeRecallIndex(state: State, path: string, now: number): void;
