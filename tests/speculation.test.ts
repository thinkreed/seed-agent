import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import type { ModelClient, ModelMessage } from "../src/model.ts";
import { Speculator, type SpeculationCandidate, type SpeculationVerdict } from "../src/speculation.ts";
import { reactSpeculationRunner } from "../src/speculation_react.ts";
import * as h from "./helpers.ts";

function candidate(overrides: Partial<SpeculationCandidate> = {}): SpeculationCandidate {
  return {
    id: "trg-spec-1",
    source: "feishu",
    text: "群友反馈 404，可能是路由缺失",
    channelIds: ["fs:oc_1"],
    ...overrides,
  };
}

test("投机执行：有价值才交付，无价值静默丢弃", async () => {
  const delivered: string[] = [];
  const verdicts: Record<string, SpeculationVerdict> = {
    "trg-spec-1": { deliver: true, summary: "确认路由缺失，已补上" },
    "trg-spec-2": { deliver: false, summary: "未复现，可能是误报" },
  };
  const speculator = new Speculator({
    runner: {
      run: async (item) => verdicts[item.id] ?? { deliver: false, summary: "unknown" },
    },
    deliver: (item, verdict) => {
      delivered.push(`${item.id}:${verdict.summary}`);
    },
    options: { sources: ["feishu"] },
    now: () => 1,
  });
  const good = await speculator.run(candidate());
  const noise = await speculator.run(candidate({ id: "trg-spec-2", text: "闲聊" }));
  assert.equal(good?.delivered, true);
  assert.equal(noise?.delivered, false);
  assert.deepEqual(delivered, ["trg-spec-1:确认路由缺失，已补上"]);
  assert.equal(speculator.stats().delivered, 1);
});

test("投机执行：来源策略、去重与并发上限", async () => {
  let runs = 0;
  const speculator = new Speculator({
    runner: {
      run: async () => {
        runs += 1;
        return { deliver: false, summary: "no" };
      },
    },
    deliver: () => undefined,
    options: { sources: ["feishu"], maxConcurrent: 1 },
    now: () => 1,
  });
  assert.equal(speculator.shouldRun(candidate({ source: "github" })), false);
  assert.equal(speculator.shouldRun(candidate()), true);
  await speculator.run(candidate());
  await speculator.run(candidate()); // 同 id 去重
  assert.equal(runs, 1);
  assert.equal(speculator.stats().skipped, 1);
});

test("投机执行：超时/异常静默丢弃，不阻塞主系统", async () => {
  const speculator = new Speculator({
    runner: { run: () => new Promise(() => undefined) },
    deliver: () => {
      throw new Error("delivery must not run");
    },
    options: { sources: ["feishu"], timeoutMs: 10 },
    now: () => 1,
  });
  const outcome = await speculator.run(candidate());
  assert.equal(outcome?.delivered, false);
  assert.match(outcome?.summary ?? "", /timeout/);
});

test("React 投机执行器：report ready 才交付，blocked 保持安静", async () => {
  const root = mkdtempSync(join(tmpdir(), "seed-spec-"));
  const clock = new FakeClock();
  const model = (reply: string): ModelClient => ({
    complete: async (_messages: readonly ModelMessage[]) => reply,
  });
  try {
    const ready = reactSpeculationRunner({ model: model('{"action":"report","status":"ready","summary":"已修复"}'), root, clock, ticket: h.ticket() });
    assert.deepEqual(await ready.run(candidate(), new AbortController().signal), {
      deliver: true,
      summary: "已修复",
    });
    const blocked = reactSpeculationRunner({ model: model('{"action":"report","status":"blocked","summary":"未复现"}'), root, clock, ticket: h.ticket() });
    assert.deepEqual(await blocked.run(candidate(), new AbortController().signal), {
      deliver: false,
      summary: "未复现",
    });
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});