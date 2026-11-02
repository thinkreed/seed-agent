import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { loadEnvFile, parseEnv } from "../src/env.ts";

test("parseEnv：注释、空行、引号、等号", () => {
  const parsed = parseEnv(
    [
      "# comment",
      "",
      "KEY=value",
      'QUOTED="hello world"',
      "SINGLE='a=b'",
      "EMPTY=",
      "MULTI=a=b=c",
    ].join("\n"),
  );
  assert.equal(parsed.KEY, "value");
  assert.equal(parsed.QUOTED, "hello world");
  assert.equal(parsed.SINGLE, "a=b");
  assert.equal(parsed.EMPTY, "");
  assert.equal(parsed.MULTI, "a=b=c");
});

test("loadEnvFile：已存在的变量不被覆盖，文件缺失静默跳过", () => {
  const dir = mkdtempSync(join(tmpdir(), "seed-env-"));
  const path = join(dir, ".env");
  writeFileSync(path, "A=from-file\nB=from-file\n");
  const env: Record<string, string | undefined> = { B: "already-set" };
  loadEnvFile(path, env);
  assert.equal(env.A, "from-file");
  assert.equal(env.B, "already-set");

  const before = Object.keys(env).length;
  loadEnvFile(join(dir, "missing.env"), env);
  assert.equal(Object.keys(env).length, before);
  rmSync(dir, { recursive: true, force: true });
});