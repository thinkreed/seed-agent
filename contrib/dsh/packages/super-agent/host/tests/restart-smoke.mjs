/**
 * 重启恢复：host 第一次运行留下 running assignment；进程重启后
 * recoverAfterRestart 收口旧 assignment 并投递 resume 输入，工单重新派发。
 */
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { Context } from '@deepseek-ai/cordis'
import SuperAgentHost from '../lib/index.js'

const root = mkdtempSync(join(tmpdir(), 'dsh-super-agent-restart-'))
const dbPath = join(root, 'events.db')
const workspace = join(root, 'work')

const ctx1 = new Context()
await ctx1.plugin(SuperAgentHost, {
  dbPath,
  workspace,
  slots: 1,
  assessorMode: 'explicit',
  routerMode: 'off',
  channelsEnabled: false,
  watchdogSeconds: 0,
  sourcesEnabled: false,
})
const host1 = ctx1.superAgent
host1.ingest({
  id: 'trg-restart',
  source: 'local',
  actor: 'human',
  text: '创建 restart-a.txt',
  threadIds: ['local:restart'],
  channelIds: ['local:restart'],
  at: Math.floor(Date.now() / 1000),
})
await host1.tick()
const before = host1.snapshot().tickets[0]
console.log('before restart:', before?.state, 'assignment:', before?.assignment?.state)
await ctx1.fiber.dispose()

const ctx2 = new Context()
await ctx2.plugin(SuperAgentHost, {
  dbPath,
  workspace,
  slots: 1,
  assessorMode: 'explicit',
  routerMode: 'off',
  channelsEnabled: false,
  watchdogSeconds: 0,
  sourcesEnabled: false,
  recoverOnStart: true,
})
const host2 = ctx2.superAgent
await host2.tick()
const snapshot = host2.snapshot()
const after = snapshot.tickets[0]
console.log('recovery events:', snapshot.recovery.events)
console.log('after restart:', after?.state, 'assignment:', after?.assignment?.state)
const liveAssignment = Object.values(host2.state().assignments).some((assignment) => assignment.state !== 'ended')
console.log('live assignment:', liveAssignment)
const ok = Boolean(snapshot.recovery.events >= 1 && after?.state === 'open' && liveAssignment)
console.log(ok ? 'RESTART SMOKE OK' : 'RESTART SMOKE FAIL')
await ctx2.fiber.dispose()
process.exit(ok ? 0 : 1)