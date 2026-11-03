/**
 * Watchdog：主系统之外的独立控制回路。
 * 先做确定性判据（停滞、投递失败），再交给模型判断是否需要介入。
 */
import type { Clock } from "./clock.ts";
import type { State } from "./domain.ts";
export type FindingKind = "stalled" | "undelivered" | "source";
export interface WatchdogFinding {
    readonly kind: FindingKind;
    readonly ticketId: string;
    readonly detail: string;
}
export interface WatchdogVerdict {
    readonly action: "ok" | "intervene";
    readonly reason: string;
}
export interface WatchdogJudge {
    judge(findings: readonly WatchdogFinding[], state: State): Promise<WatchdogVerdict>;
}
/** 自然语言运维问答（文章 §6：维护者可以问它故障原因）。 */
export interface WatchdogAdvisor {
    answer(question: string, state: State): Promise<string>;
}
export interface WatchdogReport {
    readonly findings: readonly WatchdogFinding[];
    readonly verdict: WatchdogVerdict;
}
export declare class Watchdog {
    private readonly clock;
    private readonly staleSeconds;
    private readonly judge;
    private readonly advisor;
    constructor(options: {
        clock: Clock;
        staleSeconds?: number;
        judge?: WatchdogJudge;
        advisor?: WatchdogAdvisor;
    });
    check(state: State): Promise<WatchdogReport>;
    /** 自然语言问它"为什么卡住/哪里有问题"；未接模型时给出确定性摘要。 */
    ask(question: string, state: State): Promise<string>;
    findings(state: State): WatchdogFinding[];
}
