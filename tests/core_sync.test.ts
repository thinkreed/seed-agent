import assert from "node:assert/strict";
import { test } from "node:test";
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const root = join(import.meta.dirname, "..");
const src = join(root, "src");
const core = join(root, "contrib", "dsh", "packages", "super-agent", "core", "src");

function walk(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    return entry.isDirectory() ? walk(full) : [full];
  });
}

test("DSH core 中与内核共享的文件必须与 src 完全一致", () => {
  const drift: string[] = [];
  for (const file of walk(core)) {
    if (!file.endsWith(".ts")) continue;
    const rel = relative(core, file);
    if (rel === "engine.ts") continue;
    const source = join(src, rel);
    try {
      if (!statSync(source).isFile()) continue;
    } catch {
      continue;
    }
    const hash = (path: string) => createHash("sha256").update(readFileSync(path)).digest("hex");
    if (hash(source) !== hash(file)) drift.push(rel);
  }
  assert.deepEqual(drift, [], `core drift: run node scripts/sync-core.mjs (${drift.join(", ")})`);
});