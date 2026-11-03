/** 极简 .env 读取（零依赖）：KEY=VALUE，支持 # 注释与引号；已存在的环境变量不覆盖。 */
export declare function parseEnv(text: string): Record<string, string>;
export declare function loadEnvFile(path: string, env: Record<string, string | undefined>): void;
/** 默认依次尝试 seed.env、.env（都不覆盖已有变量）。 */
export declare function loadDefaultEnv(env: Record<string, string | undefined>): void;
/** 合并进程环境、env 文件与显式覆盖；显式覆盖优先级最高。 */
export declare function mergeEnv(overrides: Readonly<Record<string, string | undefined>> | undefined, envFile?: string, base?: Record<string, string | undefined>): Record<string, string | undefined>;
