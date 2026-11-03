/** 极简 .env 读取（零依赖）：KEY=VALUE，支持 # 注释与引号；已存在的环境变量不覆盖。 */
import { existsSync, readFileSync } from "node:fs";
export function parseEnv(text) {
    const result = {};
    for (const line of text.split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith("#"))
            continue;
        const eq = trimmed.indexOf("=");
        if (eq <= 0)
            continue;
        const key = trimmed.slice(0, eq).trim();
        let value = trimmed.slice(eq + 1).trim();
        if ((value.startsWith('"') && value.endsWith('"')) ||
            (value.startsWith("'") && value.endsWith("'"))) {
            value = value.slice(1, -1);
        }
        if (key)
            result[key] = value;
    }
    return result;
}
export function loadEnvFile(path, env) {
    if (!existsSync(path))
        return;
    for (const [key, value] of Object.entries(parseEnv(readFileSync(path, "utf8")))) {
        if (env[key] === undefined)
            env[key] = value;
    }
}
/** 默认依次尝试 seed.env、.env（都不覆盖已有变量）。 */
export function loadDefaultEnv(env) {
    loadEnvFile("seed.env", env);
    loadEnvFile(".env", env);
}
/** 合并进程环境、env 文件与显式覆盖；显式覆盖优先级最高。 */
export function mergeEnv(overrides, envFile, base = { ...process.env }) {
    if (envFile)
        loadEnvFile(envFile, base);
    else
        loadDefaultEnv(base);
    return { ...base, ...(overrides ?? {}) };
}
//# sourceMappingURL=env.js.map