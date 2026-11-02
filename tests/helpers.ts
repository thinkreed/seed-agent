/** 测试构造器：集中造对象，避免每个用例重复。 */

import type {
  AcceptMode,
  Assignment,
  Attention,
  Channel,
  Decision,
  Input,
  Mandate,
  Policy,
  Report,
  ReportStatus,
  Subscription,
  Ticket,
  Thread,
  Trigger,
} from "../src/domain.ts";
import { buildPolicy } from "../src/policy.ts";

export function trigger(id = "trg-1", overrides: Partial<Trigger> = {}): Trigger {
  return {
    id,
    source: "local",
    actor: "alice",
    text: "do the thing",
    threadIds: ["thr-1"],
    channelIds: ["chan-1"],
    at: 0,
    ...overrides,
  };
}

export function policy(options: { allow?: boolean; mode?: AcceptMode } = {}): Policy {
  const allow = options.allow ?? true;
  return buildPolicy(
    [{ source: "local", actor: "*", allow, strength: "explicit", note: "test" }],
    options.mode ?? "auto",
    [["local", "*"]],
  );
}

export function mandate(version = "v1"): Mandate {
  return {
    policyVersion: version,
    strength: "explicit",
    scope: "ticket",
    source: "local",
    actor: "alice",
    rules: ["test"],
    triggerId: "trg-1",
  };
}

export function ticket(id = "tk-1", overrides: Partial<Ticket> = {}): Ticket {
  return {
    id,
    shortName: "t-000001",
    mandate: mandate(),
    threadIds: ["thr-1"],
    channelIds: ["chan-1"],
    state: "open",
    stopped: false,
    createdAt: 0,
    ...overrides,
  };
}

export function assignment(id = "as-1", overrides: Partial<Assignment> = {}): Assignment {
  return {
    id,
    ticketId: "tk-1",
    state: "pending",
    executorRef: "",
    createdAt: 0,
    ...overrides,
  };
}

export function report(
  status: ReportStatus,
  options: { ticketId?: string; assignmentId?: string; at?: number; summary?: string } = {},
): Report {
  return {
    ticketId: options.ticketId ?? "tk-1",
    assignmentId: options.assignmentId ?? "as-1",
    status,
    summary: options.summary ?? "",
    at: options.at ?? 0,
  };
}

export function accept(reason = "asked"): Decision {
  return { kind: "accept", strength: "explicit", reason, rules: [], scope: "ticket" };
}

export function ignore(reason = "chatter"): Decision {
  return { kind: "ignore", strength: "inferred", reason, rules: [], scope: "ticket" };
}

export function stop(reason = "person asked"): Decision {
  return { kind: "stop", strength: "explicit", reason, rules: [], scope: "ticket" };
}

export function input(id = "inp-1", overrides: Partial<Input> = {}): Input {
  return { id, ticketId: "tk-1", kind: "trigger", ref: "trg-1", at: 0, ...overrides };
}

export function attention(id = "att-1", ticketId = "tk-1"): Attention {
  return { id, ticketId, question: "merge or not?", at: 0 };
}

export function subscription(ticketId = "tk-1", threadId = "thr-1", kind: "own" | "context" = "own"): Subscription {
  return { ticketId, threadId, kind };
}

export function thread(id = "thr-1"): Thread {
  return { id, source: "local", at: 0 };
}

export function channel(id = "chan-1", threadId = "thr-1"): Channel {
  return { id, threadId, address: "chan-1" };
}