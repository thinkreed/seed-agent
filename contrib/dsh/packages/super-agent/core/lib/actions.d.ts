/** 派工与 effects 处理器：把"要做的事"变成事件，副作用经 outbox。 */
import type { Clock } from "./clock.ts";
import type { Policy, Report } from "./domain.ts";
import type { Effects } from "./effects.ts";
import type { AnyEvent } from "./events.ts";
import type { IdFactory } from "./ids.ts";
import type { Executor, ChannelWriter } from "./ports.ts";
import type { SqliteStore } from "./store.ts";
export interface ActionsOptions {
    readonly store: SqliteStore;
    readonly clock: Clock;
    readonly ids: IdFactory;
    readonly executor: Executor;
    readonly channels?: ChannelWriter;
}
export declare class Actions {
    private readonly store;
    private readonly clock;
    private readonly ids;
    private readonly executor;
    private readonly channels;
    constructor(options: ActionsOptions);
    /** 给空闲工单派活：受并发槽限制。只有"从未派过工"或"有新输入未投递"的工单才启动新 Assignment。
     */
    dispatch(slots: number, effects: Effects): AnyEvent[];
    /** effects: launch —— 真正启动执行器。 */
    launch(assignmentId: string): Promise<AnyEvent[]>;
    /** effects: deliver —— 把输入投递给执行器。 */
    deliver(inputId: string): Promise<AnyEvent[]>;
    /** effects: send —— 通过信道把消息发出去。 */
    send(messageId: string): Promise<AnyEvent[]>;
    /** 人的消息进入工单：结束的工单会被 resume（被 stop 的除外）。 */
    personMessage(ticketId: string, text: string, effects: Effects): AnyEvent[];
    /** 执行器报告：结束 assignment；ready/dropped 直接结束工单。 */
    report(report: Report): AnyEvent[];
    /** 运维重试：结束当前 assignment，并投递一条 retry 输入让工单重新排到执行器。 */
    retry(ticketId: string, effects: Effects): AnyEvent[];
    /** 进程重启恢复：收口所有 running assignment，并留下恢复注记。 */
    recoverAfterRestart(effects: Effects): AnyEvent[];
    /** 维护者/看门狗在线改策略：只追加事件，Gate 立即按新版本判断。 */
    setPolicy(policy: Policy): AnyEvent[];
    private stopQuietly;
    private makeInput;
}
