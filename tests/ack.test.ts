import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { ev } from "../src/builders.ts";
import { Effects } from "../src/effects.ts";
import { Router } from "../src/router.ts";
import { SqliteStore } from "../src/store.ts";

test("工单受理后 Router 先发即时确认，不等待 Worker", () => {
  const store = new SqliteStore(":memory:");
  const clock = new FakeClock();
  store.append(
    ev.ticketOpened(
      {
        id: "tk-1",
        shortName: "t-1",
        title: "核对 agent 执行链路",
        mandate: {
          policyVersion: "p",
          strength: "explicit",
          scope: "ticket",
          source: "feishu",
          actor: "u",
          rules: [],
          triggerId: "trg-1",
        },
        threadIds: ["fs:oc_1"],
        channelIds: ["fs:oc_1"],
        state: "open",
        stopped: false,
        createdAt: 0,
      },
      0,
    ),
  );
  const router = new Router({ store, clock, effects: new Effects(store, clock, { send: () => [] }) });
  const events = router.queueReplies();
  const queued = events.find((event) => event.type === "message.queued");
  assert.ok(queued);
  assert.match(JSON.stringify(queued.data), /已收到，正在处理/);
  assert.match(JSON.stringify(queued.data), /核对 agent 执行链路/);
  store.close();
});