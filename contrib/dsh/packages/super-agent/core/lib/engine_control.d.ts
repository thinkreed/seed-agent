/** Engine 的 Worker 交回/退订操作；放在独立文件保持 engine.ts 的行数纪律。 */
import type { Clock } from "./clock.ts";
import type { State } from "./domain.ts";
import type { AnyEvent } from "./events.ts";
import type { IdFactory } from "./ids.ts";
type Append = (events: readonly AnyEvent[]) => AnyEvent[];
export declare function unsubscribeFrom(state: State, clock: Clock, append: Append, ticketId: string, threadId?: string): AnyEvent[];
export declare function handBack(state: State, clock: Clock, ids: IdFactory, append: Append, ticketId: string): AnyEvent[];
export {};
