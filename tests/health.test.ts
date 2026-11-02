import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { parseConfig } from "../src/config.ts";
import { createCheckers, formatChecks, runChecks, type CheckDeps } from "../src/health.ts";

function baseConfig(overrides: Record<string, unknown> = {}) {
  return parseConfig({
    dbPath: join(mkdtempSync(join(tmpdir(), "seed-doc-")), "state.db"),
    workRoot: join(mkdtempSync(join(tmpdir(), "seed-work-")), "work"),
    model: { baseUrl: "http://127.0.0.1:1234", apiKeyEnv: "TEST_KEY", name: "m" },
    sources: { local: { inbox: "inbox.jsonl" } },
    ...overrides,
  });
}

function deps(env: Record<string, string | undefined>, options: Partial<CheckDeps> = {}): CheckDeps {
  return {
    env,
    gh: async (args) => {
      if (args[0] === "auth") return { stdout: "Logged in to github.com account tester" };
      return { stdout: "tester\n" };
    },
    fetchImpl: async () => new Response("{}", { status: 200 }),
    ...options,
  };
}

test("全部就绪时 required 检查通过", async () => {
  const checks = await runChecks(createCheckers(baseConfig(), deps({ TEST_KEY: "k" })));
  assert.equal(checks.filter((check) => check.required && !check.ok).length, 0);
  assert.match(formatChecks(checks), /OK\s+model\.key/);
});

test("缺模型 key：model.key 失败且 required", async () => {
  const checks = await runChecks(createCheckers(baseConfig(), deps({})));
  const modelKey = checks.find((check) => check.name === "model.key");
  assert.equal(modelKey?.ok, false);
  assert.equal(modelKey?.required, true);
});

test("模型端点 401：model.endpoint 失败", async () => {
  const checks = await runChecks(
    createCheckers(
      baseConfig(),
      deps({ TEST_KEY: "k" }, { fetchImpl: async () => new Response("denied", { status: 401 }) }),
    ),
  );
  const endpoint = checks.find((check) => check.name === "model.endpoint");
  assert.equal(endpoint?.ok, false);
  assert.match(endpoint?.detail ?? "", /401/);
});

test("gh 未登录：github.auth 失败", async () => {
  const checks = await runChecks(
    createCheckers(
      baseConfig(),
      deps({ TEST_KEY: "k" }, {
        gh: async () => {
          throw new Error("not logged in");
        },
      }),
    ),
  );
  const auth = checks.find((check) => check.name === "github.auth");
  assert.equal(auth?.ok, false);
});

test("配置了飞书但缺凭证：feishu.token 失败", async () => {
  const config = baseConfig({
    sources: {
      local: { inbox: "inbox.jsonl" },
      feishu: { appIdEnv: "FS_ID", appSecretEnv: "FS_SECRET", chatIds: ["oc_1"] },
    },
  });
  const checks = await runChecks(createCheckers(config, deps({ TEST_KEY: "k" })));
  const token = checks.find((check) => check.name === "feishu.token");
  assert.equal(token?.ok, false);
  assert.match(token?.detail ?? "", /missing FS_ID/);
});

test("飞书 token 正常时通过", async () => {
  const config = baseConfig({
    sources: {
      local: { inbox: "inbox.jsonl" },
      feishu: { appIdEnv: "FS_ID", appSecretEnv: "FS_SECRET", chatIds: ["oc_1"] },
    },
  });
  const checks = await runChecks(
    createCheckers(
      config,
      deps({ TEST_KEY: "k", FS_ID: "id", FS_SECRET: "sec" }, {
        fetchImpl: async () =>
          new Response(JSON.stringify({ code: 0, tenant_access_token: "t-1" }), { status: 200 }),
      }),
    ),
  );
  const token = checks.find((check) => check.name === "feishu.token");
  assert.equal(token?.ok, true);
});

test("文件系统可写检查：正常目录通过", async () => {
  const checks = await runChecks(createCheckers(baseConfig(), deps({ TEST_KEY: "k" })));
  assert.equal(checks.find((check) => check.name === "fs.writable")?.ok, true);
});