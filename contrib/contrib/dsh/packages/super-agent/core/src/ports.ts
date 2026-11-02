/** 端口定义：引擎只依赖这些接口，不依赖具体实现。 */

import type {
  Assignment,
  Channel,
  Decision,
  Input,
  Policy,
  Ticket,
  Trigger,
} from "./domain.ts";

/** Assessment（Slow Path）的输入：只读快照，不允许副作用。 */
export interface AssessContext {
  readonly threadId: string;
  readonly triggers: readonly Trigger[];
  /** 同 Thread 更早的事件（Inline & Spill：时空相邻上下文）。 */
  readonly history?: readonly Trigger[];
  readonly tickets: readonly Ticket[];
  readonly policy: Policy | null;
}

export interface Assessor {
  /** 可以是同步脚本替身，也可以是真实 LLM 的异步调用。 */
  assess(context: AssessContext): Decision | Promise<Decision>;
}

export interface Executor {
  launch(assignment: Assignment, ticket: Ticket): void | Promise<void>;
  deliver(ticket: Ticket, input: Input): void | Promise<void>;
  stop(assignment: Assignment): void | Promise<void>;
}

export interface ChannelWriter {
  send(channel: Channel, text: string): void | Promise<void>;
}

export interface Source {
  readonly name: string;
  /** 允许同步（本地剧本）或异步（网络 API）。 */
  poll(): Trigger[] | Promise<Trigger[]>;
}