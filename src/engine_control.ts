/** Engine 的 Worker 交回/退订操作；放在独立文件保持 engine.ts 的行数纪律。 */

import type { Clock } from "./clock.ts";
import type { State } from "./domain.ts";
import { ev } from "./builders.ts";
import type { AnyEvent } from "./events.ts";
import type { IdFactory } from "./ids.ts";

type Append = (events: readonly AnyEvent[]) => AnyEvent[];

export function unsubscribeFrom(
  state: State,
  clock: Clock,
  append: Append,
  ticketId: string,
  threadId?: string,
): AnyEvent[] {
  const removed = state.subscriptions.filter(
    (item) => item.ticketId === ticketId && (threadId === undefined || item.threadId === threadId),
  );
  return append(removed.map((item) => ev.subscriptionRemoved(ticketId, item.threadId, clock.now())));
}

export function handBack(
  state: State,
  clock: Clock,
  ids: IdFactory,
  append: Append,
  ticketId: string,
): AnyEvent[] {
  const ticket = state.tickets[ticketId];
  if (!ticket) throw new Error(`unknown ticket ${ticketId}`);
  const now = clock.now();
  const threadIds = state.subscriptions
    .filter((item) => item.ticketId === ticketId)
    .map((item) => item.threadId);
  const produced: AnyEvent[] = threadIds.map((threadId) => ev.subscriptionRemoved(ticketId, threadId, now));
  for (const threadId of threadIds) {
    const latest = Object.values(state.triggers)
      .filter((trigger) => trigger.threadIds.includes(threadId))
      .sort((a, b) => a.at - b.at || a.id.localeCompare(b.id))
      .at(-1);
    if (!latest) continue;
    const queued = Object.values(state.evals).find(
      (item) => item.threadId === threadId && item.state === "queued",
    );
    const triggerIds = queued ? [...queued.triggerIds, latest.id] : [latest.id];
    produced.push(ev.dispositionRecorded(latest.id, "queued", now));
    produced.push(
      ev.evalQueued({
        id: queued?.id ?? ids.next("eval"),
        threadId,
        triggerIds,
        state: "queued",
        at: now,
      }, now),
    );
  }
  return append(produced);
}