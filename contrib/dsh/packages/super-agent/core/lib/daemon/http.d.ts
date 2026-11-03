/**
 * HTTP daemon：把 DaemonAgent 暴露成可跨机器访问的执行环境（文章 §5.2）。
 * 只执行命令/读写文件并回报；不保存会话状态，重启后由计算侧 recover() 重拉。
 */
import { type Server } from "node:http";
import { type Server as HttpsServer } from "node:https";
import type { Clock } from "../clock.ts";
export interface HttpDaemonOptions {
    readonly root: string;
    readonly clock: Clock;
    readonly env?: Readonly<Record<string, string>>;
    readonly token?: string;
    readonly host?: string;
    readonly port?: number;
    /** 事件缓冲上限（默认 1000）。 */
    readonly maxEvents?: number;
    /** 直接启用 TLS；生产也可由反向代理终止 TLS。 */
    readonly tls?: {
        readonly cert: string;
        readonly key: string;
    };
}
export interface RunningDaemon {
    readonly server: Server | HttpsServer;
    readonly port: number;
    close(): Promise<void>;
}
export declare function startHttpDaemon(options: HttpDaemonOptions): Promise<RunningDaemon>;
