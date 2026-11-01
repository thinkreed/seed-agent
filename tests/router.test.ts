import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import { RecordingChannel } from "../src/channels/recording.ts";
import { RecordingExecutor, ScriptedAssessor } from "../src/fakes.ts";
import { Router, TemplateComposer } from "../src/router.ts";
import { Runtime } from "../src/runtime.ts";
import * as h from "./helpers.ts";

function setup(slots = 1) {
  const clock = new FakeClock();
  const channel = new RecordingChannel();
  const rt = Runtime.build({
    assessor: new ScriptedAssessor([h.accept()]),
    executor: new RecordingExecutor(),
    config: { policy: h.policy(), slots, channels: channel },
    clock,
  });
  const router = new Router({ store: rt.store, clock, effects: rt.engine.effects });
  return { rt, clock, channel, router };
}

async function readyTicket() {
  const ctx = setup();
  ctx.rt.engine.ingest(h.trigger());
  await ctx.rt.tickUntilIdle();
  const ticket = Object.values(ctx.rt.engine.state.tickets)[0];
  const assignment = Object.values(ctx.rt.engine.state.assignments)[0];
  assert.ok(ticket && assignment);
  ctx.rt.engine.report(
    h.report("ready", { ticketId: ticket.id, assignmentId: assignment.id, summary: "已提 PR" }),
  );
  return { ...ctx, ticket };
}

test("ready 报告会被通知一次，且内容简短", async () => {
  const { rt, router, channel } = await readyTicket();
  router.queueReplies();
  await rt.engine.tick();
  assert.equal(channel.sent.length, 1);
  assert.match(channel.sent[0]?.text ?? "", /已完成/);
  assert.match(channel.sent[0]?.text ?? "", /已提 PR/);
  rt.close();
});

test("同一条报告不会重复通知", async () => {
  const { rt, router, channel } = await readyTicket();
  router.queueReplies();
  await rt.engine.tick();
  router.queueReplies();
  await rt.engine.tick();
  assert.equal(channel.sent.length, 1);
  rt.close();
});

test("blocked 报告通知措辞是「需要你决定」", async () => {
  const { rt, clock, channel } = setup();
  rt.engine.ingest(h.trigger());
  await rt.tickUntilIdle();
  const ticket = Object.values(rt.engine.state.tickets)[0];
  const assignment = Object.values(rt.engine.state.assignments)[0];
  assert.ok(ticket && assignment);
  rt.engine.report(
    h.report("blocked", { ticketId: ticket.id, assignmentId: assignment.id, summary: "要不要合并？" }),
  );
  const router = new Router({ store: rt.store, clock, effects: rt.engine.effects });
  router.queueReplies();
  await rt.engine.tick();
  assert.match(channel.sent[0]?.text ?? "", /需要你决定/);
  rt.close();
});

test("发送失败会进 outbox 退避，恢复后补发", async () => {
  const { rt, router, channel, clock } = await readyTicket();
  channel.failTimes = 1;
  router.queueReplies();
  await rt.engine.tick();
  assert.equal(channel.sent.length, 0);
  clock.advance(2);
  await rt.engine.tick();
  assert.equal(channel.sent.length, 1);
  rt.close();
});

test("TemplateComposer：不同状态给出不同措辞", () => {
  const composer = new TemplateComposer();
  const ticket = h.ticket();
  assert.match(composer.compose(ticket, h.report("ready", { summary: "完成" }), "person/review"), /已完成/);
  assert.match(composer.compose(ticket, h.report("blocked", { summary: "缺权限" }), "person/blocked"), /需要你决定/);
  assert.match(composer.compose(ticket, h.report("failed", { summary: "崩了" }), "person/failed"), /失败/);
});