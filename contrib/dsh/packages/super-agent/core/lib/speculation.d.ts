/**
 * 投机执行（文章 §3.4）：后台先做，有价值才交付；没价值静默丢弃。
 *
 * 与具体执行器解耦：runner 只负责"尝试"，Speculator 负责来源策略、去重、
 * 并发上限、超时与"只交付有价值结果"的闸门。
 */
export interface SpeculationCandidate {
    readonly id: string;
    readonly source: string;
    readonly text: string;
    readonly channelIds: readonly string[];
    readonly threadIds?: readonly string[];
}
export interface SpeculationVerdict {
    readonly deliver: boolean;
    readonly summary: string;
}
export interface SpeculationRunner {
    run(candidate: SpeculationCandidate, signal: AbortSignal): Promise<SpeculationVerdict>;
}
export interface SpeculationOutcome {
    readonly candidateId: string;
    readonly source: string;
    readonly delivered: boolean;
    readonly summary: string;
    readonly at: number;
}
export interface SpeculationOptions {
    /** 只对这些 Source 自动投机；手动 run 不受限。 */
    readonly sources: readonly string[];
    readonly maxConcurrent?: number;
    readonly timeoutMs?: number;
    readonly dedupeLimit?: number;
}
export interface SpeculatorSettings {
    readonly runner: SpeculationRunner;
    readonly deliver: (candidate: SpeculationCandidate, verdict: SpeculationVerdict) => void | Promise<void>;
    readonly options: SpeculationOptions;
    readonly now?: () => number;
}
export declare class Speculator {
    private readonly runner;
    private readonly deliver;
    private readonly options;
    private readonly now;
    private readonly seen;
    private readonly history;
    private active;
    private skipped;
    private failed;
    constructor(settings: SpeculatorSettings);
    shouldRun(candidate: SpeculationCandidate): boolean;
    /** 后台尝试；返回 undefined 表示按策略跳过（来源不匹配/重复/并发已满）。 */
    run(candidate: SpeculationCandidate): Promise<SpeculationOutcome | undefined>;
    get outcomes(): readonly SpeculationOutcome[];
    stats(): {
        active: number;
        skipped: number;
        failed: number;
        delivered: number;
        total: number;
    };
}
