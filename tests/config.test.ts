import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { defaultConfig, loadConfig, parseConfig } from "../src/config.ts";

test("默认配置可用", () => {
  const config = defaultConfig();
  assert.equal(config.slots, 4);
  assert.equal(config.dbPath, "seed.db");
  assert.ok(config.policy.rules.length >= 1);
});

test("parseConfig：覆盖字段并派生 Policy 版本", () => {
  const config = parseConfig({
    dbPath: ":memory:",
    slots: 2,
    intervalMs: 50,
    staleSeconds: 60,
    policy: {
      acceptMode: "record",
      allowedSenders: [["github", "*"]],
      rules: [{ source: "github", actor: "*", allow: true, strength: "inferred", note: "repo" }],
    },
    worker: { file: "node", args: ["-e", "1"] },
  });
  assert.equal(config.slots, 2);
  assert.equal(config.intervalMs, 50);
  assert.equal(config.policy.acceptMode, "record");
  assert.equal(config.policy.version.length, 12);
  assert.equal(config.worker?.file, "node");
});

test("parseConfig：非法类型给出明确错误", () => {
  assert.throws(() => parseConfig([]), /must be a JSON object/);
  assert.throws(() => parseConfig({ slots: 0 }), /slots must be a positive integer/);
  assert.throws(() => parseConfig({ slots: "x" }), /slots must be a positive integer/);
  assert.throws(() => parseConfig({ policy: { acceptMode: "nope" } }), /acceptMode/);
  assert.throws(() => parseConfig({ policy: { rules: [{}] } }), /policy\.rules\[0\]\.source/);
  assert.throws(() => parseConfig({ worker: {} }), /worker\.file must be a non-empty string/);
  assert.throws(() => parseConfig({ worker: { file: "n", args: [1] } }), /worker\.args must be string\[\]/);
});

test("loadConfig：读文件；缺省返回默认", () => {
  const dir = mkdtempSync(join(tmpdir(), "seed-config-"));
  const path = join(dir, "seed.config.json");
  writeFileSync(path, JSON.stringify({ slots: 7 }));
  assert.equal(loadConfig(path).slots, 7);
  assert.equal(loadConfig().slots, defaultConfig().slots);
  rmSync(dir, { recursive: true, force: true });
});

test("parseConfig：Router 可用独立轻量模型", () => {
  const config = parseConfig({
    model: { baseUrl: "http://worker", name: "strong" },
    routerModel: { baseUrl: "http://router", name: "light", apiKeyEnv: "ROUTER_KEY" },
  });
  assert.equal(config.model?.name, "strong");
  assert.equal(config.routerModel?.name, "light");
  assert.equal(config.routerModel?.apiKeyEnv, "ROUTER_KEY");
});

test("parseConfig：未知字段被忽略", () => {
  const config = parseConfig({ slots: 3, unknown: { deep: true } });
  assert.equal(config.slots, 3);
});