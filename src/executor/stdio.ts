/** stdio 传输：把 daemon 当成独立进程启动，按行收发 JSON。 */

import { type ChildProcess, spawn } from "node:child_process";
import { createInterface } from "node:readline";

import type { DaemonEvent, DaemonRequest, DaemonResponse, Transport } from "./protocol.ts";

export interface StdioTransportOptions {
  readonly command: string;
  readonly args?: readonly string[];
  readonly cwd?: string;
  readonly env?: Readonly<Record<string, string>>;
}

interface Pending {
  resolve(response: DaemonResponse): void;
  reject(error: Error): void;
}

export class StdioTransport implements Transport {
  private readonly child: ChildProcess;
  private readonly pending = new Map<string, Pending>();
  private handler: (event: DaemonEvent) => void = () => undefined;

  constructor(options: StdioTransportOptions) {
    this.child = spawn(options.command, [...(options.args ?? [])], {
      cwd: options.cwd,
      env: { ...process.env, ...options.env } as Record<string, string>,
      stdio: ["pipe", "pipe", "inherit"],
    });
    if (this.child.stdout) {
      createInterface({ input: this.child.stdout }).on("line", (line) => this.onLine(line));
    }
    this.child.on("exit", (code) => this.onExit(code));
  }

  onEvent(handler: (event: DaemonEvent) => void): void {
    this.handler = handler;
  }

  send(request: DaemonRequest): Promise<DaemonResponse> {
    return new Promise((resolve, reject) => {
      if (!this.child.stdin?.writable) {
        reject(new Error("daemon stdin is not writable"));
        return;
      }
      this.pending.set(request.id, { resolve, reject });
      this.child.stdin.write(`${JSON.stringify(request)}\n`);
    });
  }

  close(): void {
    this.child.kill();
  }

  get pid(): number | undefined {
    return this.child.pid;
  }

  private onLine(line: string): void {
    const raw = line.trim();
    if (!raw) return;
    let payload: unknown;
    try {
      payload = JSON.parse(raw);
    } catch {
      return;
    }
    if (isEvent(payload)) {
      this.handler(payload);
      return;
    }
    const response = payload as DaemonResponse;
    const pending = this.pending.get(response.id);
    if (!pending) return;
    this.pending.delete(response.id);
    pending.resolve(response);
  }

  private onExit(code: number | null): void {
    const error = new Error(`daemon exited (code ${String(code)})`);
    for (const pending of this.pending.values()) pending.reject(error);
    this.pending.clear();
  }
}

function isEvent(payload: unknown): payload is DaemonEvent {
  return (
    payload !== null &&
    typeof payload === "object" &&
    (payload as { type?: unknown }).type === "report"
  );
}