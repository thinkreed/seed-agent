/**
 * 桌面窗口：用系统自带的 Edge/Chrome 应用模式（WebView2/Chromium 内核）打开本地控制台。
 * 零 npm 依赖；窗口独立、无地址栏，行为等价于一个桌面应用壳。
 */
import { spawn } from "node:child_process";
export interface BrowserCommand {
    readonly file: string;
    readonly args: readonly string[];
}
export interface DesktopWindow {
    readonly pid: number | undefined;
    readonly command: BrowserCommand;
    waitForExit(): Promise<void>;
    close(): void;
}
export interface DesktopOptions {
    readonly url: string;
    readonly windowSize?: string;
    readonly profileDir?: string;
    /** 覆盖浏览器命令（测试/自定义）。传 null 表示不启动浏览器。 */
    readonly browser?: BrowserCommand | null;
    readonly env?: Readonly<Record<string, string | undefined>>;
    readonly spawnImpl?: typeof spawn;
}
export declare function findBrowser(env?: Readonly<Record<string, string | undefined>>): BrowserCommand | null;
export declare function defaultProfileDir(): string;
export declare function browserArgs(url: string, options: DesktopOptions, profileDir: string): string[];
export declare function openDesktopWindow(options: DesktopOptions): DesktopWindow;
