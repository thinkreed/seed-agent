import assert from "node:assert/strict";
import { test } from "node:test";

import { buildPolicy, gate, senderAllowed } from "../src/policy.ts";
import * as h from "./helpers.ts";

test("版本由内容派生：同样规则同版本，改规则换版本", () => {
  const a = buildPolicy([{ source: "local", actor: "*", allow: true, strength: "explicit", note: "x" }], "auto", [["local", "*"]]);
  const b = buildPolicy([{ source: "local", actor: "*", allow: true, strength: "explicit", note: "x" }], "auto", [["local", "*"]]);
  const c = buildPolicy([{ source: "local", actor: "*", allow: false, strength: "explicit", note: "x" }], "auto", [["local", "*"]]);
  assert.equal(a.version, b.version);
  assert.notEqual(a.version, c.version);
  assert.notEqual(a.version, buildPolicy([...a.rules], "record", a.allowedSenders).version);
});

test("gate：无策略 / 关闭 / 非白名单 一律拒绝", () => {
  assert.equal(gate(null, h.trigger()).allowed, false);
  assert.equal(gate(h.policy({ mode: "off" }), h.trigger()).reason, "policy-off");
  const noSender = buildPolicy([], "auto", []);
  assert.equal(gate(noSender, h.trigger()).reason, "sender-not-allowed");
});

test("gate：deny 规则优先于默认", () => {
  const p = buildPolicy(
    [{ source: "local", actor: "mallory", allow: false, strength: "explicit", note: "blocked" }],
    "auto",
    [["local", "*"]],
  );
  const result = gate(p, h.trigger("trg-9", { actor: "mallory" }));
  assert.equal(result.allowed, false);
  assert.match(result.reason, /denied-by-rule/);
});

test("gate：wildcard allow 通过并带出强度", () => {
  const result = gate(h.policy(), h.trigger());
  assert.equal(result.allowed, true);
  assert.equal(result.strength, "explicit");
  assert.equal(result.rule?.source, "local");
});

test("gate：无匹配规则默认拒绝", () => {
  const p = buildPolicy([], "auto", [["github", "*"]]);
  const result = gate(p, h.trigger("trg-2", { source: "github" }));
  assert.equal(result.allowed, false);
  assert.equal(result.reason, "no-matching-rule");
});

test("senderAllowed 支持 per-source 通配", () => {
  const p = buildPolicy([], "auto", [["github", "*"]]);
  assert.equal(senderAllowed(p, "github", "anyone"), true);
  assert.equal(senderAllowed(p, "local", "anyone"), false);
});