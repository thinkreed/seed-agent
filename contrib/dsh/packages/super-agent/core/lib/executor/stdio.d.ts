/** stdio 传输：把 daemon 当成独立进程启动，按行收发 JSON。 */
import type { DaemonEvent, DaemonRequest, DaemonResponse, Transport } from "./protocol.ts";
export interface StdioTransportOptions {
    readonly command: string;
    readonly args?: readonly string[];
    readonly cwd?: string;
    readonly env?: Readonly<Record<string, string>>;
}
export declare class StdioTransport implements Transport {
    private readonly child;
    private readonly pending;
    private handler;
    constructor(options: StdioTransportOptions);
    onEvent(handler: (event: DaemonEvent) => void): void;
    send(request: DaemonRequest): Promise<DaemonResponse>;
    close(): void;
    get pid(): number | undefined;
    private onLine;
    private onExit;
}
