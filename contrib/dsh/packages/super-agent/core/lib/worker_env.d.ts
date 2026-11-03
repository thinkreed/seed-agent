/**
 * Worker 子进程环境最小化：只透传运行所需的基础变量，绝不把宿主上的
 * 飞书/GitHub/云厂商等无关凭据带进执行环境（文章 §8.4 的最小隔离）。
 */
/** 生成 worker 的基础环境变量（不含任何凭据）。 */
export declare function workerBaseEnv(base?: Readonly<Record<string, string | undefined>>): Record<string, string>;
/** 只挑出需要的凭据（例如 worker 自己的模型 key），用于显式注入。 */
export declare function pickSecrets(secrets: Readonly<Record<string, string | undefined>>): Record<string, string>;
