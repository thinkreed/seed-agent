/**
 * Router：面向人的那一层。
 * 只做两件事：把"需要人看/需要人决定"的结果变成一条短消息，并交给信道发出去。
 */
import type { Clock } from "./clock.ts";
import type { Report, Stage, Ticket } from "./domain.ts";
import type { Effects } from "./effects.ts";
import type { AnyEvent } from "./events.ts";
import type { SqliteStore } from "./store.ts";
export interface ReplyComposer {
    compose(ticket: Ticket, report: Report, stage: Stage): string;
}
export declare class TemplateComposer implements ReplyComposer {
    compose(_ticket: Ticket, report: Report, stage: Stage): string;
}
export interface RouterOptions {
    readonly store: SqliteStore;
    readonly clock: Clock;
    readonly effects: Effects;
    readonly composer?: ReplyComposer;
}
export declare class Router {
    private readonly store;
    private readonly clock;
    private readonly effects;
    private readonly composer;
    constructor(options: RouterOptions);
    /** 为"需要人"的结果排队一条消息；同一条报告只通知一次。 */
    queueReplies(): AnyEvent[];
}
