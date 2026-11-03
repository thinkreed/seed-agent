/**
 * 健康检查：doctor 命令用。全部是真实探测（网络/进程/文件系统），不做写外部服务的动作。
 */
import type { SeedConfig } from "./config.ts";
export interface HealthCheck {
    readonly name: string;
    readonly required: boolean;
    readonly ok: boolean;
    readonly detail: string;
}
export interface Checker {
    readonly name: string;
    readonly required: boolean;
    run(): Promise<{
        ok: boolean;
        detail: string;
    }>;
}
export interface CheckDeps {
    readonly env: Readonly<Record<string, string | undefined>>;
    /** 覆盖 gh 调用（测试用）。 */
    readonly gh?: (args: string[]) => Promise<{
        stdout: string;
    }>;
    /** 覆盖 HTTP 探测（测试用）。 */
    readonly fetchImpl?: typeof fetch;
}
export declare function createCheckers(config: SeedConfig, deps: CheckDeps): Checker[];
export declare function runChecks(checkers: readonly Checker[]): Promise<HealthCheck[]>;
export declare function formatChecks(checks: readonly HealthCheck[]): string;
