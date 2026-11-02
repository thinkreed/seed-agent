import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { WatchdogController } from "../src/control.ts";
import { Runtime } from "../src/runtime.ts";
import { SourceRunner } from "../src/runner.ts";
import type { Trigger } from "../src/domain.ts";
import { Watchdog } from "../src/watchdog.ts";
import { RecordingExecutor, ScriptedAssessor } from "./fakes.ts";
import * as h from "./helpers.ts";

class FlakySource {
  readonly name = "flaky";
  fail = true;
  triggers: Trigger[] = [h.trigger("trg-1")];

  poll(): Trigger[] {
    if (this.fail) throw new Error("api timeout");
    return this.triggers;
  }
}

test("Source 失败/恢复：状态记录 sourceFailures，Watchdog 能给出 source finding", async () => {
  const clock = new FakeClock();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([h.accept()]),
    executor: new RecordingExecutor(),
    config: { dbPath: ":memory:", policy: h.policy() },
    clock,
  });
  const source = new FlakySource();
  const runner = new SourceRunner({ sources: [source], engine: rt.engine, store: rt.store, clock });

  const failed = await runner.pollOnce();
  assert.equal(failed.failures.length, 1);
  assert.match(rt.engine.state.sourceFailures.flaky ?? "", /api timeout/);

  const findings = new Watchdog({ clock }).findings(rt.engine.state);
  assert.ok(findings.some((finding) => finding.kind === "source" && finding.detail.includes("flaky")));

  const report = await new Watchdog({ clock }).check(rt.engine.state);
  const outcome = new WatchdogController(rt.engine).apply(report);
  assert.ok(outcome.applied.some((item) => item.kind === "source" && item.action === "none"));

  source.fail = false;
  await runner.pollOnce();
  assert.equal(rt.engine.state.sourceFailures.flaky, undefined);
  rt.close();
});

test("Source 只记录一次失败事件，重复失败不刷事件", async () => {
  const clock = new FakeClock();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([]),
    executor: new RecordingExecutor(),
    config: { dbPath: ":memory:", policy: h.policy() },
    clock,
  });
  const source = new FlakySource();
  const runner = new SourceRunner({ sources: [source], engine: rt.engine, store: rt.store, clock });
  await runner.pollOnce();
  const afterFirst = rt.store.lastSeq();
  await runner.pollOnce();
  assert.equal(rt.store.lastSeq(), afterFirst);
  rt.close();
});