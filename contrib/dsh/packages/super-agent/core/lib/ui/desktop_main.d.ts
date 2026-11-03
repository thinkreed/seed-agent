/**
 * `node src/cli.ts desktop [config]`：常驻引擎 + 本地控制台 + 独立应用窗口。
 */
export interface DesktopRunOptions {
    readonly configPath?: string;
    readonly port?: number;
    /** false = 只起服务，不打开窗口。 */
    readonly window?: boolean;
}
export declare function runDesktop(options?: DesktopRunOptions): Promise<number>;
