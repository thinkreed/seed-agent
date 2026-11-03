/** 远端 daemon 配置解析（与主配置解析分开，保持单文件行数）。 */

export interface RemoteConfig {
  readonly url: string;
  readonly tokenEnv?: string;
}

export function parseRemote(raw: unknown): RemoteConfig {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) throw new Error("remote must be an object");
  const source = raw as Record<string, unknown>;
  return {
    url: requiredString(source.url, "remote.url"),
    ...(source.tokenEnv === undefined ? {} : { tokenEnv: requiredString(source.tokenEnv, "remote.tokenEnv") }),
  };
}

function requiredString(value: unknown, name: string): string {
  if (typeof value !== "string" || value.trim() === "") throw new Error(`${name} must be a non-empty string`);
  return value.trim();
}