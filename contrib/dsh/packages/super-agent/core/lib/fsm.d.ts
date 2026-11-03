/** 工单阶段派生与合法转换检查。阶段只从 State 计算，绝不落库。 */
import type { Stage, State, Ticket } from "./domain.ts";
export declare class TransitionError extends Error {
    constructor(message: string);
}
export declare function stageOf(state: State, ticket: Ticket): Stage;
export declare function requiresPerson(stage: Stage): boolean;
export declare function assertCanEnd(ticket: Ticket, reason?: string): void;
