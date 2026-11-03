/**
 * `node src/cli.ts desktop [config]`：常驻引擎 + 本地控制台 + 独立应用窗口。
 */
import { App } from "../app.js";
import { loadConfig } from "../config.js";
import { openDesktopWindow } from "./desktop.js";
import { createUiServer } from "./server.js";
export async function runDesktop(options = {}) {
    const config = loadConfig(options.configPath);
    const app = App.create({ config });
    const server = await createUiServer({
        runtime: app.runtime,
        port: options.port ?? 4780,
        slots: config.slots,
    });
    const running = app.run();
    running.catch((error) => {
        process.stderr.write(`engine stopped: ${String(error)}\n`);
    });
    process.stdout.write(`seed-agent desktop: ${server.url}\n`);
    if (options.window === false) {
        process.stdout.write("no-browser mode: Ctrl+C to stop\n");
        await new Promise((resolve) => {
            process.once("SIGINT", () => resolve());
            process.once("SIGTERM", () => resolve());
        });
    }
    else {
        const window = openDesktopWindow({ url: server.url });
        process.stdout.write(`window pid: ${String(window.pid ?? "?")}\n`);
        await window.waitForExit();
    }
    app.stop();
    await server.close();
    return 0;
}
//# sourceMappingURL=desktop_main.js.map