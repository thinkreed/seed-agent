/** 命令行入口：run（真实运行） / panel（只读面板）。 */

import { App } from "./app.ts";
import { loadConfig } from "./config.ts";
import { loadDefaultEnv, loadEnvFile } from "./env.ts";
import { read as feishuRead, say as feishuSay } from "./feishu_cli.ts";
import { createCheckers, formatChecks, runChecks } from "./health.ts";
import { render, renderJson } from "./panel.ts";
import { SqliteStore } from "./store.ts";
import { runDesktop } from "./ui/desktop_main.ts";

/** 真实运行：配置驱动，接真实模型与渠道。 */
export async function runApp(configPath: string | undefined, once: boolean): Promise<number> {
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

export function showPanel(path: string, asJson = false): number {
  const store = new SqliteStore(path);
  console.log(asJson ? renderJson(store.state()) : render(store.state()));
  store.close();
  return 0;
}

/** 真实体检：凭证、端点、gh、飞书、文件系统。 */
export async function doctor(configPath?: string): Promise<number> {
  const config = loadConfig(configPath);
  const env: Record<string, string | undefined> = { ...process.env };
  if (process.env.SEED_ENV_FILE) loadEnvFile(process.env.SEED_ENV_FILE, env);
  else loadDefaultEnv(env);
  const checks = await runChecks(createCheckers(config, { env }));
  console.log(formatChecks(checks));
  const failed = checks.filter((check) => !check.ok && check.required);
  if (failed.length > 0) console.error(`\n${failed.length} required check(s) failed`);
  return failed.length === 0 ? 0 : 1;
}

/** 桌面控制台：常驻引擎 + 本地界面（默认 4780，独立应用窗口）。 */
export async function desktopCommand(configPath?: string, argv: string[] = []): Promise<number> {
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
const exitCode =
  command === "run"
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
              : 2;
if (exitCode === 2) {
  console.error(
    "usage: cli.ts run <config.json> [--once] | desktop <config.json> [--port 4780] [--no-browser] | doctor <config.json> | panel <db> [--json] | say <chat_id> <text> | read <chat_id>",
  );
}
process.exitCode = exitCode;