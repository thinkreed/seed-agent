/**
 * Watchdog：主系统之外的独立控制回路。
 * 先做确定性判据（停滞、投递失败），再交给模型判断是否需要介入。
 */

import type { Clock } from "./clock.ts";
import type { State } from "./domain.ts";

export type FindingKind = "stalled" | "undelivered";

export interface WatchdogFinding {
  readonly kind: FindingKind;
  readonly ticketId: string;
  readonly detail: string;
}

export interface WatchdogVerdict {
  readonly action: "ok" | "intervene";
  readonly reason: string;
}

export interface WatchdogJudge {
  judge(findings: readonly WatchdogFinding[], state: State): Promise<WatchdogVerdict>;
}

export interface WatchdogReport {
  readonly findings: readonly WatchdogFinding[];
  readonly verdict: WatchdogVerdict;
}

export class Watchdog {
  private readonly clock: Clock;
  private readonly staleSeconds: number;
  private readonly judge: WatchdogJudge | undefined;

  constructor(options: { clock: Clock; staleSeconds?: number; judge?: WatchdogJudge }) {
    this.clock = options.clock;
    this.staleSeconds = options.staleSeconds ?? 1800;
    this.judge = options.judge;
  }

  async check(state: State): Promise<WatchdogReport> {
    const findings = this.findings(state);
    if (findings.length === 0) return { findings, verdict: { action: "ok", reason: "quiet" } };
    if (!this.judge) {
      return { findings, verdict: { action: "intervene", reason: "deterministic-findings" } };
    }
    return { findings, verdict: await this.judge.judge(findings, state) };
  }

  findings(state: State): WatchdogFinding[] {
    const now = this.clock.now();
    const collected: WatchdogFinding[] = [];

    for (const inputId of state.undelivered) {
      const input = state.inputs[inputId];
      if (!input) continue;
      collected.push({
        kind: "undelivered",
        ticketId: input.ticketId,
        detail: `input ${inputId} failed to reach its executor`,
      });
    }

    for (const ticket of Object.values(state.tickets)) {
      if (ticket.state !== "open") continue;
      const last = lastActivity(state, ticket.id) ?? ticket.createdAt;
      if (now - last >= this.staleSeconds) {
        collected.push({
          kind: "stalled",
          ticketId: ticket.id,
          detail: `no activity for ${Math.round(now - last)}s`,
        });
      }
    }
    return collected;
  }
}

function lastActivity(state: State, ticketId: string): number | undefined {
  const times: number[] = [];
  for (const assignment of Object.values(state.assignments)) {
    if (assignment.ticketId === ticketId) times.push(assignment.createdAt);
  }
  for (const input of Object.values(state.inputs)) {
    if (input.ticketId === ticketId) times.push(input.at);
  }
  for (const report of state.reports[ticketId] ?? []) times.push(report.at);
  return times.length > 0 ? Math.max(...times) : undefined;
}