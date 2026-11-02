/** daemon 协议：计算侧与执行环境之间的唯一契约（可跑在 stdio / 网络 / 内存上）。 */

export interface WorkerSpec {
  readonly file: string;
  readonly args?: readonly string[];
}

export type DaemonRequest =
  | {
      readonly id: string;
      readonly cmd: "launch";
      readonly assignmentId: string;
      readonly ticketId: string;
      readonly shortName: string;
      readonly scope: string;
      readonly worker: WorkerSpec;
      readonly prepare?: WorkerSpec;
    }
  | {
      readonly id: string;
      readonly cmd: "deliver";
      readonly ticketId: string;
      readonly inputId: string;
      readonly kind: string;
      readonly ref: string;
    }
  | { readonly id: string; readonly cmd: "stop"; readonly ticketId: string };

export type DaemonResponse =
  | { readonly id: string; readonly ok: true }
  | { readonly id: string; readonly ok: false; readonly error: string };

export interface DaemonReportEvent {
  readonly type: "report";
  readonly ticketId: string;
  readonly assignmentId: string;
  readonly status: string;
  readonly summary: string;
  readonly at: number;
}

export type DaemonEvent = DaemonReportEvent;

/** 传输层：daemon 只认这个接口，测试可用内存实现，生产可用 stdio/WebSocket。 */
export interface Transport {
  send(request: DaemonRequest): Promise<DaemonResponse>;
  onEvent(handler: (event: DaemonEvent) => void): void;
  close(): void;
}