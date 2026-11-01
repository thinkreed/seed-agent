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
  readonly tickets: readonly Ticket[];
  readonly policy: Policy | null;
}

export interface Assessor {
  assess(context: AssessContext): Decision;
}

export interface Executor {
  launch(assignment: Assignment, ticket: Ticket): void;
  deliver(ticket: Ticket, input: Input): void;
  stop(assignment: Assignment): void;
}

export interface ChannelWriter {
  send(channel: Channel, text: string): void;
}

export interface Source {
  readonly name: string;
  poll(): Trigger[];
}