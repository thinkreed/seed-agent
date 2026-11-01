/**
 * Router：面向人的那一层。
 * 只做两件事：把"需要人看/需要人决定"的结果变成一条短消息，并交给信道发出去。
 */

import { ev } from "./builders.ts";
import type { Clock } from "./clock.ts";
import type { OutboundMessage, Report, Stage, Ticket } from "./domain.ts";
import { ticketReport } from "./domain.ts";
import type { Effects } from "./effects.ts";
import type { AnyEvent } from "./events.ts";
import { stageOf } from "./fsm.ts";
import type { SqliteStore } from "./store.ts";

const NOTIFY_STATUSES: ReadonlySet<string> = new Set(["ready", "blocked", "failed"]);

export interface ReplyComposer {
  compose(ticket: Ticket, report: Report, stage: Stage): string;
}

export class TemplateComposer implements ReplyComposer {
  compose(_ticket: Ticket, report: Report, stage: Stage): string {
    const summary = report.summary || "（无补充说明）";
    if (report.status === "ready") return `已完成：${summary}。请验收。`;
    if (report.status === "blocked") return `需要你决定：${summary}`;
    if (report.status === "failed") return `执行失败：${summary}`;
    return `进展：${summary}（${stage}）`;
  }
}

export interface RouterOptions {
  readonly store: SqliteStore;
  readonly clock: Clock;
  readonly effects: Effects;
  readonly composer?: ReplyComposer;
}

export class Router {
  private readonly store: SqliteStore;
  private readonly clock: Clock;
  private readonly effects: Effects;
  private readonly composer: ReplyComposer;

  constructor(options: RouterOptions) {
    this.store = options.store;
    this.clock = options.clock;
    this.effects = options.effects;
    this.composer = options.composer ?? new TemplateComposer();
  }

  /** 为"需要人"的结果排队一条消息；同一条报告只通知一次。 */
  queueReplies(): AnyEvent[] {
    const state = this.store.state();
    const produced: AnyEvent[] = [];
    for (const ticket of Object.values(state.tickets).sort((a, b) => a.id.localeCompare(b.id))) {
      if (ticket.stopped) continue;
      const report = ticketReport(state, ticket.id);
      if (!report || !NOTIFY_STATUSES.has(report.status)) continue;
      const address = ticket.channelIds[0];
      if (!address) continue;
      const messageId = `msg:${ticket.id}:${report.at}`;
      if (state.messages[messageId]) continue;
      const message: OutboundMessage = {
        id: messageId,
        ticketId: ticket.id,
        channelId: address,
        address,
        text: this.composer.compose(ticket, report, stageOf(state, ticket)),
        at: this.clock.now(),
      };
      produced.push(ev.messageQueued(message, this.clock.now()));
      this.effects.enqueue(`eff:${messageId}`, "send", { messageId }, this.clock.now());
    }
    return produced.length > 0 ? this.store.appendAll(produced) : [];
  }
}