import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { Runtime } from "../src/runtime.ts";
import { RecordingExecutor } from "./fakes.ts";
import * as h from "./helpers.ts";

test("accept 决策的 title 成为工单语义标题", async () => {
  const clock = new FakeClock();
  const rt = Runtime.build({
    assessor: {
      assess: () => ({
        ...h.accept(),
        title: "核对 agent 执行链路",
      }),
    },
    executor: new RecordingExecutor(),
    config: { dbPath: ":memory:", policy: h.policy() },
    clock,
  });
  try {
    rt.engine.ingest(h.trigger("trg-1", { threadIds: ["thr-title"] }));
    await rt.tickUntilIdle();
    const ticket = Object.values(rt.engine.state.tickets)[0];
    assert.equal(ticket?.title, "核对 agent 执行链路");
  } finally {
    rt.close();
  }
});