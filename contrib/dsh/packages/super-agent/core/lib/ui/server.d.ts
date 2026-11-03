/**
 * 桌面控制台的本地 HTTP 服务：静态资源 + JSON API + SSE。
 * 只绑定 127.0.0.1；可选 token 校验，默认关闭（本机单用户）。
 */
import type { Runtime } from "../runtime.ts";
export interface UiServerOptions {
    readonly runtime: Runtime;
    readonly port?: number;
    readonly host?: string;
    readonly token?: string;
    readonly webDir?: string;
    readonly slots?: number;
    /** SSE 推送间隔（毫秒）。 */
    readonly tickMs?: number;
}
export interface UiServer {
    readonly url: string;
    readonly port: number;
    close(): Promise<void>;
}
export declare function createUiServer(options: UiServerOptions): Promise<UiServer>;
