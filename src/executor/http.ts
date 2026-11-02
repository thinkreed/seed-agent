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

export class HttpTransport implements Transport {
  private readonly baseUrl: string;
  private readonly token: string | undefined;
  private readonly pollMs: number;
  private readonly fetchImpl: typeof fetch;
  private readonly reconnect: (() => void) | undefined;
  private handler: (event: DaemonEvent) => void = () => undefined;
  private latest = 0;
  private closed = false;
  private online = false;
  private attempted = false;
  private timer: ReturnType<typeof setTimeout> | undefined;

  constructor(options: HttpTransportOptions) {
    this.baseUrl = options.url.replace(/\/+$/, "");
    this.token = options.token;
    this.pollMs = options.pollMs ?? 250;
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.reconnect = options.onReconnect;
    this.schedule(0);
  }

  onEvent(handler: (event: DaemonEvent) => void): void {
    this.handler = handler;
  }

  async send(request: DaemonRequest): Promise<DaemonResponse> {
    const response = await this.fetchImpl(`${this.baseUrl}/request`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(request),
    });
    const payload = (await response.json()) as DaemonResponse;
    if (!response.ok) {
      const error = (payload as { error?: string }).error ?? `daemon HTTP ${response.status}`;
      throw new Error(error);
    }
    return payload;
  }

  close(): void {
    this.closed = true;
    if (this.timer) clearTimeout(this.timer);
  }

  private headers(): Record<string, string> {
    return {
      "content-type": "application/json",
      ...(this.token ? { authorization: `Bearer ${this.token}` } : {}),
    };
  }

  private schedule(delay: number): void {
    if (this.closed) return;
    this.timer = setTimeout(() => {
      void this.poll();
    }, delay);
    if (typeof this.timer === "object" && "unref" in this.timer) this.timer.unref();
  }

  private async poll(): Promise<void> {
    if (this.closed) return;
    try {
      const response = await this.fetchImpl(`${this.baseUrl}/events?after=${this.latest}`, {
        headers: this.headers(),
      });
      // 设备从离线恢复：通知上层重拉 Assignment / 补投输入（文章 §5.2）。
      if (this.attempted && !this.online) this.reconnect?.();
      this.attempted = true;
      this.online = true;
      if (response.ok) {
        const payload = (await response.json()) as {
          events?: { seq: number; event: DaemonEvent }[];
        };
        for (const item of payload.events ?? []) {
          if (item.seq > this.latest) this.latest = item.seq;
          this.handler(item.event);
        }
      }
    } catch {
      this.attempted = true;
      this.online = false;
      // daemon 暂时离线：下次轮询继续，由 effects 退避/恢复负责重投。
    }
    this.schedule(this.pollMs);
  }
}