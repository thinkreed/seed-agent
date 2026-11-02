import assert from "node:assert/strict";
import { test } from "node:test";

import type { Report, Ticket } from "../src/domain.ts";
import { emptyState } from "../src/domain.ts";
import type { ModelClient, ModelMessage } from "../src/model.ts";
import { LlmWatchdogJudge } from "../src/watchdog_llm.ts";
import { Watchdog } from "../src/watchdog.ts";

class RecordingModel implements ModelClient {
  readonly messages: (readonly ModelMessage[])[] = [];
  private readonly reply: string;

  constructor(reply: string) {
    this.reply = reply;
  }

  async complete(messages: readonly ModelMessage[]): Promise<string> {
    this.messages.push(messages);
    return this.reply;
  }
}

function stateWithTicket(): { state: ReturnType<typeof emptyState>; ticket: Ticket } {
  const state = emptyState();
  const ticket: Ticket = {
    id: "tk-1",
    shortName: "t-1",
    mandate: {
      policyVersion: "",
      strength: "explicit",
      scope: "ticket",
      source: "local",
      actor: "a",
      rules: [],
      triggerId: "",
    },
    threadIds: ["thr-1"],
    channelIds: [],
    state: "open",
    stopped: false,
    createdAt: 0,
  };
  return { state: { ...state, tickets: { [ticket.id]: ticket } }, ticket };
}

function report(): Report {
  return { ticketId: "tk-1", assignmentId: "as-1", status: "waiting", summary: "", at: 0 };
}

test("模型判定 intervene -> verdict.intervene", async () => {
  const { state } = stateWithTicket();
  const model = new RecordingModel('{"action":"intervene","reason":"ticket stuck"}');
  const verdict = await new LlmWatchdogJudge(model).judge(
    [{ kind: "stalled", ticketId: "tk-1", detail: "no activity" }],
    state,
  );
  assert.equal(verdict.action, "intervene");
  assert.equal(verdict.reason, "ticket stuck");
  assert.match(model.messages[0]?.[1]?.content ?? "", /no activity/);
});

test("模型判定 ok / 乱答 -> verdict.ok", async () => {
  const { state } = stateWithTicket();
  for (const reply of ['{"action":"ok","reason":"fine"}', "not json", '{"action":"weird"}']) {
    const verdict = await new LlmWatchdogJudge(new RecordingModel(reply)).judge(
      [{ kind: "stalled", ticketId: "tk-1", detail: "x" }],
      state,
    );
    assert.equal(verdict.action, "ok");
  }
});

test("findings 截断后再交给模型", async () => {
  const { state } = stateWithTicket();
  const model = new RecordingModel('{"action":"ok","reason":"fine"}');
  const findings = Array.from({ length: 30 }, (_, index) => ({
    kind: "stalled" as const,
    ticketId: `tk-${index}`,
    detail: `detail-${index}`,
  }));
  await new LlmWatchdogJudge(model, 5).judge(findings, state);
  const content = model.messages[0]?.[1]?.content ?? "";
  assert.match(content, /detail-4/);
  assert.doesNotMatch(content, /detail-5/);
});

test("模型裁定带上了最近报告与原始请求，用于判断是否真在推进", async () => {
  const state = stateWithTicket().state;
  const enriched = {
    ...state,
    reports: { "tk-1": [{ ...report(), status: "progress" as const, summary: "正在跑测试" }] },
    triggers: {
      "trg-1": {
        id: "trg-1",
        source: "local",
        actor: "alice",
        text: "修复登录 404",
        threadIds: ["thr-1"],
        channelIds: ["chan-1"],
        at: 1,
      },
    },
  };
  const model = new RecordingModel('{"action":"ok","reason":"still moving"}');
  await new LlmWatchdogJudge(model).judge([], enriched);
  const content = model.messages[0]?.[1]?.content ?? "";
  assert.match(content, /修复登录 404/);
  assert.match(content, /正在跑测试/);
});

test("Watchdog：有 open 工单时即使没有 finding 也交给模型判断", async () => {
  const { state } = stateWithTicket();
  const model = new RecordingModel('{"action":"intervene","reason":"direction drifted"}');
  const watchdog = new Watchdog({ clock: { now: () => 10 }, judge: new LlmWatchdogJudge(model) });
  const report = await watchdog.check(state);
  assert.equal(report.findings.length, 0);
  assert.equal(report.verdict.action, "intervene");
  assert.match(report.verdict.reason, /drifted/);
});

void report;