/**
 * HTTP 传输：计算侧通过 HTTP 访问远端 daemon（BYOM / 跨设备）。
 * daemon 的 /events 提供增量报告；轮询即可，不引入 WebSocket 依赖。
 */
export class HttpTransport {
    baseUrl;
    token;
    pollMs;
    fetchImpl;
    reconnect;
    handler = () => undefined;
    latest = 0;
    closed = false;
    online = false;
    attempted = false;
    timer;
    constructor(options) {
        this.baseUrl = options.url.replace(/\/+$/, "");
        this.token = options.token;
        this.pollMs = options.pollMs ?? 250;
        this.fetchImpl = options.fetchImpl ?? fetch;
        this.reconnect = options.onReconnect;
        this.schedule(0);
    }
    onEvent(handler) {
        this.handler = handler;
    }
    async send(request) {
        const response = await this.fetchImpl(`${this.baseUrl}/request`, {
            method: "POST",
            headers: this.headers(),
            body: JSON.stringify(request),
        });
        const payload = (await response.json());
        if (!response.ok) {
            const error = payload.error ?? `daemon HTTP ${response.status}`;
            throw new Error(error);
        }
        return payload;
    }
    close() {
        this.closed = true;
        if (this.timer)
            clearTimeout(this.timer);
    }
    headers() {
        return {
            "content-type": "application/json",
            ...(this.token ? { authorization: `Bearer ${this.token}` } : {}),
        };
    }
    schedule(delay) {
        if (this.closed)
            return;
        this.timer = setTimeout(() => {
            void this.poll();
        }, delay);
        if (typeof this.timer === "object" && "unref" in this.timer)
            this.timer.unref();
    }
    async poll() {
        if (this.closed)
            return;
        try {
            const response = await this.fetchImpl(`${this.baseUrl}/events?after=${this.latest}`, {
                headers: this.headers(),
            });
            // 设备从离线恢复：通知上层重拉 Assignment / 补投输入（文章 §5.2）。
            if (this.attempted && !this.online)
                this.reconnect?.();
            this.attempted = true;
            this.online = true;
            if (response.ok) {
                const payload = (await response.json());
                for (const item of payload.events ?? []) {
                    if (item.seq > this.latest)
                        this.latest = item.seq;
                    this.handler(item.event);
                }
            }
        }
        catch {
            this.attempted = true;
            this.online = false;
            // daemon 暂时离线：下次轮询继续，由 effects 退避/恢复负责重投。
        }
        this.schedule(this.pollMs);
    }
}
//# sourceMappingURL=http.js.map