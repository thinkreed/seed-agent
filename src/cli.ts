/** 命令行入口：run（真实运行） / panel（只读面板）。 */

import { App } from "./app.ts";
import { loadConfig } from "./config.ts";
import { render, renderJson } from "./panel.ts";
import { SqliteStore } from "./store.ts";

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

const [, , command = "help", arg, flag] = process.argv;
const exitCode =
  command === "run"
    ? await runApp(arg, flag === "--once")
    : command === "panel"
      ? showPanel(arg ?? "seed.db", flag === "--json")
      : 2;
if (exitCode === 2) {
  console.error("usage: node src/cli.ts run <config.json> [--once] | panel <db> [--json]");
}
process.exitCode = exitCode;