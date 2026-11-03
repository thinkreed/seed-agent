import assert from "node:assert/strict";
import { test } from "node:test";
import { existsSync } from "node:fs";
import { join } from "node:path";

const root = join(import.meta.dirname, "..");

test("DSH core 不再保留第二份内核源码", () => {
  const coreSrc = join(root, "contrib", "dsh", "packages", "super-agent", "core", "src");
  assert.equal(existsSync(coreSrc), false, "core/src must not exist; build from the canonical src");
});