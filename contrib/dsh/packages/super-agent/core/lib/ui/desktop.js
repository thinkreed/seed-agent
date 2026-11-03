/**
 * 桌面窗口：用系统自带的 Edge/Chrome 应用模式（WebView2/Chromium 内核）打开本地控制台。
 * 零 npm 依赖；窗口独立、无地址栏，行为等价于一个桌面应用壳。
 */
import { spawn } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
const WINDOWS_BROWSERS = [
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
];
export function findBrowser(env = process.env) {
    const override = env.SEED_BROWSER;
    if (override && existsSync(override))
        return { file: override, args: [] };
    if (process.platform === "win32") {
        const found = WINDOWS_BROWSERS.find((path) => existsSync(path));
        return found ? { file: found, args: [] } : null;
    }
    if (process.platform === "darwin")
        return { file: "open", args: ["-W"] };
    return { file: "xdg-open", args: [] };
}
export function defaultProfileDir() {
    const base = process.env.LOCALAPPDATA ?? join(homedir(), ".local", "share");
    return join(base, "seed-agent", "ui-profile");
}
export function browserArgs(url, options, profileDir) {
    if (process.platform === "win32") {
        return [
            `--app=${url}`,
            `--window-size=${options.windowSize ?? "1440,920"}`,
            `--user-data-dir=${profileDir}`,
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-features=Translate,msEdgeIdentityIntegration",
        ];
    }
    return [url];
}
export function openDesktopWindow(options) {
    const browser = options.browser === undefined ? findBrowser(options.env) : options.browser;
    if (!browser)
        throw new Error("no browser found: set SEED_BROWSER to an Edge/Chrome executable");
    const profileDir = options.profileDir ?? defaultProfileDir();
    mkdirSync(profileDir, { recursive: true });
    const args = [...browser.args, ...browserArgs(options.url, options, profileDir)];
    const child = (options.spawnImpl ?? spawn)(browser.file, args, {
        detached: false,
        stdio: "ignore",
        // 必须为 false：STARTF_USESHOWWINDOW + SW_HIDE 会把 --app 窗口也隐藏。
        windowsHide: false,
        windowsVerbatimArguments: false,
    });
    const exited = new Promise((resolve) => {
        child.on("exit", () => resolve());
        child.on("error", () => resolve());
    });
    return {
        pid: child.pid,
        command: { file: browser.file, args },
        waitForExit: () => exited,
        close: () => {
            if (child.exitCode === null && child.pid !== undefined)
                child.kill();
        },
    };
}
//# sourceMappingURL=desktop.js.map