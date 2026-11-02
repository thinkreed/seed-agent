/**
 * Worker 子进程环境最小化：只透传运行所需的基础变量，绝不把宿主上的
 * 飞书/GitHub/云厂商等无关凭据带进执行环境（文章 §8.4 的最小隔离）。
 */

const ALLOWED = [
  "PATH",
  "Path",
  "PATHEXT",
  "SystemRoot",
  "SystemDrive",
  "windir",
  "COMSPEC",
  "TEMP",
  "TMP",
  "HOME",
  "USERPROFILE",
  "APPDATA",
  "LOCALAPPDATA",
  "PROGRAMDATA",
  "PROGRAMFILES",
  "PROGRAMFILES(X86)",
  "NUMBER_OF_PROCESSORS",
  "PROCESSOR_ARCHITECTURE",
  "PROCESSOR_IDENTIFIER",
  "OS",
  "LANG",
  "LC_ALL",
  "HTTP_PROXY",
  "HTTPS_PROXY",
  "NO_PROXY",
  "http_proxy",
  "https_proxy",
  "no_proxy",
] as const;

/** 生成 worker 的基础环境变量（不含任何凭据）。 */
export function workerBaseEnv(
  base: Readonly<Record<string, string | undefined>> = process.env,
): Record<string, string> {
  const env: Record<string, string> = {};
  for (const key of ALLOWED) {
    const value = base[key];
    if (value !== undefined) env[key] = value;
  }
  return env;
}

/** 只挑出需要的凭据（例如 worker 自己的模型 key），用于显式注入。 */
export function pickSecrets(
  secrets: Readonly<Record<string, string | undefined>>,
): Record<string, string> {
  const env: Record<string, string> = {};
  for (const [key, value] of Object.entries(secrets)) {
    if (value !== undefined && value !== "") env[key] = value;
  }
  return env;
}