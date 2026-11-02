/**
 * `node src/cli.ts desktop [config]`：常驻引擎 + 本地控制台 + 独立应用窗口。
 */

import { App } from "../app.ts";
import { loadConfig } from "../config.ts";
import { openDesktopWindow } from "./desktop.ts";
import { createUiServer } from "./server.ts";

export interface DesktopRunOptions {
  readonly configPath?: string;
  readonly port?: number;
  /** false = 只起服务，不打开窗口。 */
  readonly window?: boolean;
}

export async function runDesktop(options: DesktopRunOptions = {}): Promise<number> {
  const config = loadConfig(options.configPath);
  const app = App.create({ config });
  const server = await createUiServer({
    runtime: app.runtime,
    port: options.port ?? 4780,
    slots: config.slots,
  });

  const running = app.run();
  running.catch((error: unknown) => {
    process.stderr.write(`engine stopped: ${String(error)}\n`);
  });

  process.stdout.write(`seed-agent desktop: ${server.url}\n`);
  if (options.window === false) {
    process.stdout.write("no-browser mode: Ctrl+C to stop\n");
    await new Promise<void>((resolve) => {
      process.once("SIGINT", () => resolve());
      process.once("SIGTERM", () => resolve());
    });
  } else {
    const window = openDesktopWindow({ url: server.url });
    process.stdout.write(`window pid: ${String(window.pid ?? "?")}\n`);
    await window.waitForExit();
  }

  app.stop();
  await server.close();
  return 0;
}