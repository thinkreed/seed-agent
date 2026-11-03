/** 远端 daemon 配置解析（与主配置解析分开，保持单文件行数）。 */
export function parseRemote(raw) {
    if (raw === null || typeof raw !== "object" || Array.isArray(raw))
        throw new Error("remote must be an object");
    const source = raw;
    return {
        url: requiredString(source.url, "remote.url"),
        ...(source.tokenEnv === undefined ? {} : { tokenEnv: requiredString(source.tokenEnv, "remote.tokenEnv") }),
    };
}
function requiredString(value, name) {
    if (typeof value !== "string" || value.trim() === "")
        throw new Error(`${name} must be a non-empty string`);
    return value.trim();
}
//# sourceMappingURL=config_parse_remote.js.map