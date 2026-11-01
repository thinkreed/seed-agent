import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { backoffDelay, Effects } from "../src/effects.ts";
import { SqliteStore } from "../src/store.ts";

test("退避表单调递增并封顶", () => {
  const backoff = { schedule: [2, 4, 8], maxAttempts: 4 };
  assert.equal(backoffDelay(backoff, 0), 0);
  assert.equal(backoffDelay(backoff, 1), 2);
  assert.equal(backoffDelay(backoff, 2), 4);
  assert.equal(backoffDelay(backoff, 3), 8);
  assert.equal(backoffDelay(backoff, 9), 8);
});

test("失败两次后成功：按退避重试，最终 done", () => {
  const clock = new FakeClock();
  const store = new SqliteStore();
  let attempts = 0;
  const effects = new Effects(store, clock, {
    launch: () => {
      attempts += 1;
      if (attempts < 3) throw new Error("transient");
      return [];
    },
  });

  effects.enqueue("eff-1", "launch", {}, clock.now());
  effects.drain();
  assert.equal(store.outboxGet("eff-1")?.state, "pending");
  assert.equal(store.outboxGet("eff-1")?.attempts, 1);

  clock.advance(2);
  effects.drain();
  assert.equal(store.outboxGet("eff-1")?.attempts, 2);

  clock.advance(4);
  effects.drain();
  assert.equal(store.outboxGet("eff-1")?.state, "done");
  assert.equal(attempts, 3);
  store.close();
});

test("超过最大次数 -> dropped", () => {
  const clock = new FakeClock();
  const store = new SqliteStore();
  const effects = new Effects(
    store,
    clock,
    { launch: () => { throw new Error("always"); } },
    { schedule: [1], maxAttempts: 2 },
  );
  effects.enqueue("eff-x", "launch", {}, clock.now());
  effects.drain();
  clock.advance(1);
  effects.drain();
  assert.equal(store.outboxGet("eff-x")?.state, "dropped");
  store.close();
});

test("没有处理器的副作用立即 dropped", () => {
  const clock = new FakeClock();
  const store = new SqliteStore();
  const effects = new Effects(store, clock, {});
  effects.enqueue("eff-y", "unknown-kind", {}, clock.now());
  const { dropped } = effects.drain();
  assert.deepEqual(dropped, ["eff-y"]);
  assert.equal(store.outboxGet("eff-y")?.lastError, "no-handler");
  store.close();
});