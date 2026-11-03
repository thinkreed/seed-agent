/**
 * HTTP 传输：计算侧通过 HTTP 访问远端 daemon（BYOM / 跨设备）。
 * daemon 的 /events 提供增量报告；轮询即可，不引入 WebSocket 依赖。
 */
import type { DaemonEvent, DaemonRequest, DaemonResponse, Transport } from "./protocol.ts";
export interface HttpTransportOptions {
    readonly url: string;
    readonly token?: string;
    /** 报告轮询间隔（毫秒，默认 250）。 */
    readonly pollMs?: number;
    /** 设备重新上线时的回调（通常接 RemoteExecutor.recover）。 */
    readonly onReconnect?: () => void;
    /** 测试注入；默认全局 fetch。 */
    readonly fetchImpl?: typeof fetch;
}
export declare class HttpTransport implements Transport {
    private readonly baseUrl;
    private readonly token;
    private readonly pollMs;
    private readonly fetchImpl;
    private readonly reconnect;
    private handler;
    private latest;
    private closed;
    private online;
    private attempted;
    private timer;
    constructor(options: HttpTransportOptions);
    onEvent(handler: (event: DaemonEvent) => void): void;
    send(request: DaemonRequest): Promise<DaemonResponse>;
    close(): void;
    private headers;
    private schedule;
    private poll;
}
