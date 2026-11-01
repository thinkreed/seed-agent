import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { Daemon } from "../src/daemon.ts";
import { RecordingExecutor, ScriptedAssessor } from "./fakes.ts";
import { Runtime } from "../src/runtime.ts";
import { SourceRunner } from "../src/runner.ts";
import { LocalSource } from "../src/sources/local.ts";
import * as h from "./helpers.ts";

function setup(slots = 2) {
  const clock = new FakeClock();
  const assessor = new ScriptedAssessor([h.accept(), h.accept()]);
  const executor = new RecordingExecutor();
  const runtime = Runtime.build({
    assessor,
    executor,
    config: { policy: h.policy(), slots },
    clock,
  });
  const runner = new SourceRunner({
    sources: [new LocalSource("local", [h.trigger("trg-1"), h.trigger("trg-2", { threadIds: ["thr-2"] })])],
    engine: runtime.engine,
    store: runtime.store,
    clock,
  });
  const daemon = new Daemon({ runner, engine: runtime.engine, store: runtime.store, clock, intervalMs: 1 });
  return { daemon, runtime, clock };
}

test("runRound：收事件并驱动引擎", async () => {
  const { daemon, runtime } = setup();
  const report = await daemon.runRound();
  assert.equal(report.ingested, 2);
  assert.ok(report.events > 0);
  await runtime.tickUntilIdle();
  assert.equal(Object.keys(runtime.engine.state.tickets).length, 2);
  runtime.close();
});

test("run：达到 maxRounds 后自行退出", async () => {
  const { daemon, runtime } = setup();
  const sleep = async () => undefined;
  const rounds = await daemon.run(3);
  assert.equal(rounds, 3);
  assert.equal(daemon.roundCount, 3);
  runtime.close();
  void sleep;
});

test("stop：外部可以中止常驻循环", async () => {
  const { daemon, runtime } = setup();
  const run = daemon.run();
  daemon.stop();
  const rounds = await run;
  assert.ok(rounds >= 1);
  runtime.close();
});

test("watchdog 每轮巡检并在发现异常时动作", async () => {
  const { rt, clock } = (() => {
    const clock = new FakeClock();
    const runtime = Runtime.build({
      assessor: new ScriptedAssessor([h.accept()]),
      executor: new RecordingExecutor(),
      config: { policy: h.policy(), slots: 1 },
      clock,
    });
    return { rt: runtime, clock };
  })();
  rt.engine.ingest(h.trigger());
  await rt.tickUntilIdle();

  const findings: string[] = [];
  const bridge = {
    check: async (state: import("../src/domain.ts").State) => ({
      findings: [
        { kind: "stalled" as const, ticketId: Object.keys(state.tickets)[0] as string, detail: "test" },
      ],
      verdict: { action: "intervene" as const, reason: "test" },
    }),
    apply: (report: { findings: readonly { ticketId: string }[] }) => {
      findings.push(...report.findings.map((finding) => finding.ticketId));
    },
  };
  const runner = new SourceRunner({ sources: [], engine: rt.engine, store: rt.store, clock });
  const daemon = new Daemon({ runner, engine: rt.engine, store: rt.store, clock, watchdog: bridge });
  await daemon.runRound();
  assert.equal(findings.length, 1);
  rt.close();
});