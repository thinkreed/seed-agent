import assert from "node:assert/strict";
import { test } from "node:test";

import { buildRecallIndex } from "../src/recall_index.ts";
import type { State } from "../src/domain.ts";

test("链式召回索引能从 trigger 跳到 thread 再到 ticket", () => {
  const state = {
    triggers: {
      "trg-1": {
        id: "trg-1",
        source: "feishu",
        actor: "u",
        text: "hello",
        threadIds: ["thr-1"],
        channelIds: ["fs:oc_1"],
        at: 1,
      },
    },
    threads: { "thr-1": { id: "thr-1", source: "feishu", at: 1 } },
    tickets: {
      "tk-1": {
        id: "tk-1",
        shortName: "t-1",
        title: "核对链路",
        mandate: { triggerId: "trg-1" },
        threadIds: ["thr-1"],
        channelIds: ["fs:oc_1"],
        state: "open",
      },
    },
    reports: {},
  } as unknown as State;
  const index = buildRecallIndex(state, 2);
  assert.deepEqual(index.tickets["tk-1"], {
    shortName: "t-1",
    title: "核对链路",
    state: "open",
    threadIds: ["thr-1"],
    channelIds: ["fs:oc_1"],
    triggerId: "trg-1",
    reports: [],
  });
  assert.deepEqual((index.threads["thr-1"] as { ticketIds: string[] }).ticketIds, ["tk-1"]);
});