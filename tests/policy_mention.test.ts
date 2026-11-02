import assert from "node:assert/strict";
import { test } from "node:test";

import { buildPolicy, gate } from "../src/policy.ts";
import * as h from "./helpers.ts";

test("mention 准入：配置的 Source 必须显式 @ 才放行", () => {
  const policy = buildPolicy(
    [{ source: "feishu", actor: "*", allow: true, strength: "explicit", note: "group" }],
    "auto",
    [["feishu", "*"]],
    { mentionRequiredFor: ["feishu"], mentionTokens: ["@seed"] },
  );
  const plain = h.trigger("trg-1", { source: "feishu", text: "这个怎么又挂了" });
  assert.equal(gate(policy, plain).allowed, false);
  assert.equal(gate(policy, plain).reason, "mention-required");

  const mentioned = h.trigger("trg-2", { source: "feishu", text: "@seed 帮我看下这个报错" });
  assert.equal(gate(policy, mentioned).allowed, true);
});

test("mention 策略参与版本哈希：规则变化可在线生效", () => {
  const base = buildPolicy([], "auto", [["feishu", "*"]]);
  const withMention = buildPolicy([], "auto", [["feishu", "*"]], {
    mentionRequiredFor: ["feishu"],
    mentionTokens: ["@seed"],
  });
  assert.notEqual(base.version, withMention.version);
});