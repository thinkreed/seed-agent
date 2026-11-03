/** 内核 App 的投机执行接线：来源白名单、独立工作目录、只交付有价值结果。 */
import type { Clock } from "./clock.ts";
import type { ChannelWriter } from "./ports.ts";
import type { ModelClient } from "./model.ts";
import { Speculator } from "./speculation.ts";
export interface AppSpeculationOptions {
    readonly model: ModelClient;
    readonly channels: ChannelWriter;
    readonly clock: Clock;
    readonly root: string;
    readonly sources: readonly string[];
}
export interface AppSpeculation {
    readonly speculator: Speculator;
    readonly onTrigger: (trigger: {
        readonly id: string;
        readonly source: string;
        readonly text: string;
        readonly channelIds: readonly string[];
        readonly threadIds: readonly string[];
    }) => void;
}
export declare function buildAppSpeculation(options: AppSpeculationOptions): AppSpeculation | undefined;
