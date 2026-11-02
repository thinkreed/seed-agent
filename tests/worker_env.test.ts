import assert from "node:assert/strict";
import { test } from "node:test";

import { pickSecrets, workerBaseEnv } from "../src/worker_env.ts";

test("worker 基础环境不含宿主凭据，只保留运行必需变量", () => {
  const env = workerBaseEnv({
    PATH: "/usr/bin",
    TEMP: "/tmp",
    FEISHU_APP_SECRET: "feishu-secret",
    BAILIAN_API_KEY: "model-key",
    GITHUB_TOKEN: "gh-token",
  });
  assert.equal(env.PATH, "/usr/bin");
  assert.equal(env.TEMP, "/tmp");
  assert.equal(env.FEISHU_APP_SECRET, undefined);
  assert.equal(env.BAILIAN_API_KEY, undefined);
  assert.equal(env.GITHUB_TOKEN, undefined);
});

test("pickSecrets：只显式注入需要的密钥，忽略空值", () => {
  assert.deepEqual(pickSecrets({ BAILIAN_API_KEY: "k", EMPTY: "" }), { BAILIAN_API_KEY: "k" });
});