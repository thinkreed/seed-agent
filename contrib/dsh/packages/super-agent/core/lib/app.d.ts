/**
 * 应用装配：把真实组件接成可运行系统（无 fake）。
 * 需要真实凭证：
 *   - 模型：环境变量（默认 DEEPSEEK_API_KEY）
 *   - GitHub：`gh auth login` 已完成
 *   - 飞书：FEISHU_APP_ID / FEISHU_APP_SECRET（配置里可改名）
 */
import type { SeedConfig } from "./config.ts";
import { Daemon } from "./daemon.ts";
import { Router } from "./router.ts";
import { Runtime } from "./runtime.ts";
export { AppError } from "./app_error.ts";
export interface AppOptions {
    readonly config: SeedConfig;
    readonly env?: Readonly<Record<string, string | undefined>>;
    readonly once?: boolean;
    /** 覆盖 worker 命令（默认用内置 worker 进程）。 */
    readonly workerCommand?: {
        file: string;
        args: readonly string[];
    };
    /** 额外 env 文件（默认依次读 seed.env、.env）。 */
    readonly envFile?: string;
}
export declare class App {
    readonly runtime: Runtime;
    readonly daemon: Daemon;
    readonly router: Router;
    private readonly executor;
    private readonly closeExecutor;
    private constructor();
    static create(options: AppOptions): App;
    /** 跑一轮并等到系统收敛（单次模式/验证用）。 */
    runOnce(timeoutMs?: number): Promise<void>;
    /** 常驻运行。 */
    run(): Promise<void>;
    stop(): void;
}
