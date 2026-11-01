import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { RecordingExecutor, ScriptedAssessor } from "../src/fakes.ts";
import { SeqIds } from "../src/ids.ts";
import type { Trigger } from "../src/domain.ts";
import { Runtime } from "../src/runtime.ts";
import { SourceRunner } from "../src/runner.ts";
import { LocalSource } from "../src/sources/local.ts";
import * as h from "./helpers.ts";

function setup(slots = 2) {
  const clock = new FakeClock();
  const assessor = new ScriptedAssessor([h.accept(), h.accept(), h.accept()]);
  const executor = new RecordingExecutor();
  const rt = Runtime.build({
    assessor,
    executor,
    config: { policy: h.policy(), slots },
    clock,
    ids: new SeqIds(),
  });
  return { rt, clock, assessor, executor };
}

function triggers(count: number): Trigger[] {
  return Array.from({ length: count }, (_, index) =>
    h.trigger(`trg-${String(index + 1).padStart(3, "0")}`, { at: index }),
  );
}

test("LocalSource：按 batchSize 分批吐出，直到耗尽", async () => {
  const source = new LocalSource("local", triggers(5), { batchSize: 2 });
  assert.equal(source.poll().length, 2);
  assert.equal(source.poll().length, 2);
  assert.equal(source.poll().length, 1);
  assert.equal(source.poll().length, 0);
  assert.equal(source.remaining, 0);
});

test("SourceRunner：轮询 -> ingest -> tick，端到端出门票", async () => {
  const { rt, clock } = setup();
  const runner = new SourceRunner({
    sources: [new LocalSource("local", triggers(3))],
    engine: rt.engine,
    store: rt.store,
    clock,
  });

  const report = runner.drain();
  assert.equal(report.ingested, 3);
  assert.deepEqual(report.failures, []);
  assert.equal(rt.store.cursorGet("local"), "trg-003");

  await rt.tickUntilIdle();
  assert.equal(Object.keys(rt.engine.state.tickets).length, 1);
  rt.close();
});

test("SourceRunner：一个 Source 抛错不影响其它 Source", async () => {
  const { rt, clock } = setup();
  const broken = {
    name: "broken",
    poll: () => {
      throw new Error("network down");
    },
  };
  const runner = new SourceRunner({
    sources: [broken, new LocalSource("local", triggers(1))],
    engine: rt.engine,
    store: rt.store,
    clock,
  });
  const report = runner.drain();
  assert.equal(report.ingested, 1);
  assert.equal(report.failures.length, 1);
  assert.equal(report.failures[0]?.source, "broken");
  rt.close();
});

test("SourceRunner：重复轮询不会重复 ingest", async () => {
  const { rt, clock } = setup();
  const runner = new SourceRunner({
    sources: [new LocalSource("local", triggers(2))],
    engine: rt.engine,
    store: rt.store,
    clock,
  });
  runner.drain();
  const seq = rt.store.lastSeq();
  runner.drain();
  assert.equal(rt.store.lastSeq(), seq);
  rt.close();
});