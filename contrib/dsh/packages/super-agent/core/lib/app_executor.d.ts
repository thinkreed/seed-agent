/** 执行器装配：本地 LocalExecutor，或远端 daemon（HttpTransport + RemoteExecutor）。 */
import type { Clock } from "./clock.ts";
import type { SeedConfig } from "./config.ts";
import type { Executor } from "./ports.ts";
import type { Runtime } from "./runtime.ts";
import type { WorkerSpec } from "./executor/protocol.ts";
export interface AppExecutorOptions {
    readonly config: SeedConfig;
    readonly workerCommand?: WorkerSpec;
    readonly clock: Clock;
    readonly runtime: () => Runtime;
    readonly apiKey: string;
    readonly recallPath: string;
    readonly env: Readonly<Record<string, string | undefined>>;
}
export interface AppExecutor {
    readonly executor: Executor;
    close(): void;
}
export declare function buildAppExecutor(options: AppExecutorOptions): AppExecutor;
