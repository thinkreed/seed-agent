/**
 * 内核版投机执行器：用真实 ReactLoop 在独立目录里静默尝试。
 * 只有模型明确 report ready（确认问题且找到简单修复）才判定为可交付。
 */
import type { Clock } from "./clock.ts";
import type { Ticket } from "./domain.ts";
import { JobRegistry } from "./jobs.ts";
import type { ModelClient } from "./model.ts";
import type { SpeculationRunner } from "./speculation.ts";
export interface ReactSpeculationOptions {
    readonly model: ModelClient;
    readonly root: string;
    readonly clock: Clock;
    readonly ticket: Ticket;
    readonly jobs?: JobRegistry;
    readonly maxSteps?: number;
}
export declare function reactSpeculationRunner(options: ReactSpeculationOptions): SpeculationRunner;
