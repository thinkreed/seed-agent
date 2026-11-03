/** stdio 传输：把 daemon 当成独立进程启动，按行收发 JSON。 */
import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
export class StdioTransport {
    child;
    pending = new Map();
    handler = () => undefined;
    constructor(options) {
        this.child = spawn(options.command, [...(options.args ?? [])], {
            cwd: options.cwd,
            env: { ...process.env, ...options.env },
            stdio: ["pipe", "pipe", "inherit"],
        });
        if (this.child.stdout) {
            createInterface({ input: this.child.stdout }).on("line", (line) => this.onLine(line));
        }
        this.child.on("exit", (code, signal) => this.onExit(code, signal));
    }
    onEvent(handler) {
        this.handler = handler;
    }
    send(request) {
        return new Promise((resolve, reject) => {
            if (!this.child.stdin?.writable) {
                reject(new Error("daemon stdin is not writable"));
                return;
            }
            this.pending.set(request.id, { resolve, reject });
            this.child.stdin.write(`${JSON.stringify(request)}\n`);
        });
    }
    close() {
        this.child.kill();
    }
    get pid() {
        return this.child.pid;
    }
    onLine(line) {
        const raw = line.trim();
        if (!raw)
            return;
        let payload;
        try {
            payload = JSON.parse(raw);
        }
        catch {
            return;
        }
        if (isEvent(payload)) {
            this.handler(payload);
            return;
        }
        const response = payload;
        const pending = this.pending.get(response.id);
        if (!pending)
            return;
        this.pending.delete(response.id);
        pending.resolve(response);
    }
    onExit(code, signal) {
        const error = new Error(`daemon exited (code ${String(code)}, signal ${String(signal ?? "none")})`);
        for (const pending of this.pending.values())
            pending.reject(error);
        this.pending.clear();
    }
}
function isEvent(payload) {
    return (payload !== null &&
        typeof payload === "object" &&
        payload.type === "report");
}
//# sourceMappingURL=stdio.js.map