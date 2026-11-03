/** 内核 Worker 的链式召回索引：把事件/线程/工单投影成可逐跳读取的 JSON。 */

import { mkdirSync, renameSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

import type { State } from "./domain.ts";

export interface RecallIndex {
  readonly generatedAt: number;
  readonly triggers: Record<string, unknown>;
  readonly threads: Record<string, unknown>;
  readonly tickets: Record<string, unknown>;
}

export function buildRecallIndex(state: State, now: number): RecallIndex {
  const triggers: Record<string, unknown> = {};
  for (const trigger of Object.values(state.triggers)) {
    triggers[trigger.id] = {
      source: trigger.source,
      actor: trigger.actor,
      text: trigger.text.slice(0, 2000),
      threadIds: trigger.threadIds,
      channelIds: trigger.channelIds,
      at: trigger.at,
    };
  }
  const threads: Record<string, unknown> = {};
  for (const thread of Object.values(state.threads)) {
    threads[thread.id] = {
      triggerIds: Object.values(state.triggers)
        .filter((trigger) => trigger.threadIds.includes(thread.id))
        .map((trigger) => trigger.id),
      ticketIds: Object.values(state.tickets)
        .filter((ticket) => ticket.threadIds.includes(thread.id))
        .map((ticket) => ticket.id),
    };
  }
  const tickets: Record<string, unknown> = {};
  for (const ticket of Object.values(state.tickets)) {
    tickets[ticket.id] = {
      shortName: ticket.shortName,
      title: ticket.title,
      state: ticket.state,
      threadIds: ticket.threadIds,
      channelIds: ticket.channelIds,
      triggerId: ticket.mandate.triggerId,
      reports: (state.reports[ticket.id] ?? []).slice(-5).map((report) => ({
        status: report.status,
        summary: report.summary.slice(0, 1000),
        at: report.at,
      })),
    };
  }
  return { generatedAt: now, triggers, threads, tickets };
}

export function writeRecallIndex(state: State, path: string, now: number): void {
  mkdirSync(dirname(path), { recursive: true });
  const temp = `${path}.tmp`;
  writeFileSync(temp, JSON.stringify(buildRecallIndex(state, now)), "utf8");
  renameSync(temp, path);
}