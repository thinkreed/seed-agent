/** 配置入口：类型、默认值、加载。解析实现见 config_parse.ts。 */
import { readFileSync } from "node:fs";
import { defaultConfig, parseConfig } from "./config_parse.js";
export { defaultConfig, parseConfig };
export function loadConfig(path) {
    if (!path)
        return defaultConfig();
    return parseConfig(JSON.parse(readFileSync(path, "utf8")));
}
//# sourceMappingURL=config.js.map