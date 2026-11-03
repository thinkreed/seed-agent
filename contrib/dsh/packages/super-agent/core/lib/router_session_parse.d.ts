/** Router Session 的纯解析辅助：模型输出 → Decision/Recall（无 IO，可单测）。 */
import type { Decision } from "./domain.ts";
import type { RecallKind } from "./recall.ts";
export declare function ignored(reason: string): Decision;
export declare function parsePayload(raw: string): Record<string, unknown> | undefined;
export declare function readRecalls(payload: Record<string, unknown>): {
    kind: RecallKind;
    id: string;
}[];
export declare function readDecisions(payload: Record<string, unknown>): Map<string, Decision>;
export declare function decisionOf(record: Record<string, unknown>): Decision;
export declare function parseChatResult(raw: string): {
    reply: string;
    work?: string;
};
export declare function parseChatReply(raw: string): string;
