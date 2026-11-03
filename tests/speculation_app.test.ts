import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { FakeClock } from "../src/clock.ts";
import { buildAppSpeculation } from "../src/app_speculation.ts";
import type { ModelClient } from "../src/model.ts";

test("投机执行接入 SourceRunner 后可静默完成并交付", async () => {
  const dir = mkdtempSync(join(tmpdir(), "seed-spec-app-"));
  const sent: string[] = [];
  const model: ModelClient = {
    async complete() {
      return JSON.stringify({ action: "report", status: "ready", summary: "spec ok" });
    },
  };
  const spec = buildAppSpeculation({
    model,
    channels: { send: async (_channel, text) => { sent.push(text); } },
    clock: new FakeClock(),
    root: dir,
    sources: ["local"],
  });
  assert.ok(spec);
  spec.onTrigger({ id: "trg-1", source: "local", text: "check", channelIds: ["fs:oc_1"], threadIds: ["thr-1"] });
  const deadline = Date.now() + 1000;
  while (sent.length === 0 && Date.now() < deadline) await new Promise((resolve) => setTimeout(resolve, 5));
  assert.deepEqual(sent, ["[投机执行] spec ok"]);
  rmSync(dir, { recursive: true, force: true });
});