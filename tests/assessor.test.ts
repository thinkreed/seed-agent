import assert from "node:assert/strict";
import { test } from "node:test";

import { parseDecision } from "../src/assessor.ts";

test("解析纯 JSON", () => {
  const decision = parseDecision(
    '{"kind":"accept","strength":"explicit","reason":"asked","scope":"ticket"}',
  );
  assert.equal(decision.kind, "accept");
  assert.equal(decision.strength, "explicit");
  assert.equal(decision.reason, "asked");
});

test("解析 fenced code block", () => {
  const decision = parseDecision('```json\n{"kind":"stop","reason":"done"}\n```');
  assert.equal(decision.kind, "stop");
  assert.equal(decision.strength, "inferred");
});

test("解析前后夹带散文的 JSON", () => {
  const decision = parseDecision('I think we should not act.\n{"kind":"ignore","reason":"chatter"}\nThanks.');
  assert.equal(decision.kind, "ignore");
  assert.equal(decision.reason, "chatter");
});

test("非法 kind 降级为 ignore 并标注原因", () => {
  const decision = parseDecision('{"kind":"destroy"}');
  assert.equal(decision.kind, "ignore");
  assert.match(decision.reason, /unparsable:bad-kind/);
});

test("缺失字段使用安全默认值", () => {
  const decision = parseDecision('{"kind":"accept"}');
  assert.equal(decision.strength, "inferred");
  assert.equal(decision.scope, "ticket");
  assert.deepEqual(decision.rules, []);
});

test("rules 只保留字符串并限量", () => {
  const decision = parseDecision(
    `{"kind":"accept","rules":["r1",2,null,"r2",${JSON.stringify("r3")}]}`,
  );
  assert.deepEqual(decision.rules, ["r1", "r2", "r3"]);
});

test("无法解析时返回 ignore，不抛错", () => {
  const decision = parseDecision("not json at all");
  assert.equal(decision.kind, "ignore");
  assert.match(decision.reason, /unparsable/);
});

test("reason 超长会被截断", () => {
  const decision = parseDecision(JSON.stringify({ kind: "ignore", reason: "x".repeat(1000) }));
  assert.equal(decision.reason.length, 300);
});