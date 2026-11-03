/** 命令行入口：run（真实运行） / panel（只读面板）。 */
import { App } from "./app.js";
import { SystemClock } from "./clock.js";
import { loadConfig } from "./config.js";
import { startHttpDaemon } from "./daemon/http.js";
import { loadDefaultEnv, loadEnvFile } from "./env.js";
import { read as feishuRead, say as feishuSay } from "./feishu_cli.js";
import { createCheckers, formatChecks, runChecks } from "./health.js";
import { render, renderJson } from "./panel.js";
import { SqliteStore } from "./store.js";
import { runDesktop } from "./ui/desktop_main.js";
/** 真实运行：配置驱动，接真实模型与渠道。 */
export async function runApp(configPath, once) {
    const config = loadConfig(configPath);
    const app = App.create({ config });
    if (once) {
        await app.runOnce();
        console.log(render(app.runtime.engine.state));
        app.stop();
        return 0;
    }
    process.on("SIGINT", () => app.stop());
    process.on("SIGTERM", () => app.stop());
    await app.run();
    return 0;
}
/** 端侧 daemon：只执行、不存会话状态（BYOM / 跨设备）。 */
export async function daemonCommand(argv) {
    const root = argv.find((item) => !item.startsWith("--")) ?? process.cwd();
    const portIndex = argv.indexOf("--port");
    const port = portIndex >= 0 ? Number(argv[portIndex + 1]) : 0;
    const hostIndex = argv.indexOf("--host");
    const host = hostIndex >= 0 ? argv[hostIndex + 1] : "127.0.0.1";
    const token = process.env.SA_DAEMON_TOKEN?.trim();
    const daemon = await startHttpDaemon({
        root,
        clock: new SystemClock(),
        ...(Number.isFinite(port) && port > 0 ? { port } : {}),
        ...(host ? { host } : {}),
        ...(token ? { token } : {}),
    });
    console.log(JSON.stringify({ ok: true, port: daemon.port, root }));
    await new Promise((resolve) => {
        process.once("SIGINT", resolve);
        process.once("SIGTERM", resolve);
    });
    await daemon.close();
    return 0;
}
export function showPanel(path, asJson = false) {
    const store = new SqliteStore(path);
    console.log(asJson ? renderJson(store.state()) : render(store.state()));
    store.close();
    return 0;
}
/** 真实体检：凭证、端点、gh、飞书、文件系统。 */
export async function doctor(configPath) {
    const config = loadConfig(configPath);
    const env = { ...process.env };
    if (process.env.SEED_ENV_FILE)
        loadEnvFile(process.env.SEED_ENV_FILE, env);
    else
        loadDefaultEnv(env);
    const checks = await runChecks(createCheckers(config, { env }));
    console.log(formatChecks(checks));
    const failed = checks.filter((check) => !check.ok && check.required);
    if (failed.length > 0)
        console.error(`\n${failed.length} required check(s) failed`);
    return failed.length === 0 ? 0 : 1;
}
/** 桌面控制台：常驻引擎 + 本地界面（默认 4780，独立应用窗口）。 */
export async function desktopCommand(configPath, argv = []) {
    const portIndex = argv.indexOf("--port");
    const port = portIndex >= 0 ? Number(argv[portIndex + 1]) : undefined;
    const noBrowser = argv.includes("--no-browser");
    return runDesktop({
        ...(configPath ? { configPath } : {}),
        ...(Number.isFinite(port) && port !== undefined ? { port } : {}),
        window: !noBrowser,
    });
}
const [, , command = "help", arg, flag] = process.argv;
const exitCode = command === "run"
    ? await runApp(arg, flag === "--once")
    : command === "doctor"
        ? await doctor(arg)
        : command === "panel"
            ? showPanel(arg ?? "seed.db", flag === "--json")
            : command === "say"
                ? await feishuSay(arg ?? "", process.argv.slice(4).join(" "))
                : command === "read"
                    ? await feishuRead(arg ?? "")
                    : command === "desktop" || command === "ui"
                        ? await desktopCommand(arg, process.argv.slice(4))
                        : command === "daemon"
                            ? await daemonCommand(process.argv.slice(3))
                            : 2;
if (exitCode === 2) {
    console.error("usage: cli.ts run <config.json> [--once] | desktop <config.json> [--port 4780] [--no-browser] | daemon [root] [--port 4781] [--host 127.0.0.1] | doctor <config.json> | panel <db> [--json] | say <chat_id> <text> | read <chat_id>");
}
process.exitCode = exitCode;
//# sourceMappingURL=cli.js.map