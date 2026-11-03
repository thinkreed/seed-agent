/** reducer：唯一纯状态推导。无 IO、无时钟、无随机。 */
import type { State } from "./domain.ts";
import type { AnyEvent } from "./events.ts";
export declare class UnknownEventError extends Error {
    constructor(type: string);
}
export declare class InvalidTransitionError extends Error {
    constructor(message: string);
}
export declare function apply(state: State, event: AnyEvent): State;
export declare function rebuild(events: readonly AnyEvent[], initial?: State): State;
