/** 订阅扇出：同线程的后续消息并入已有工单，不新建工单。 */
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { Context } from '@deepseek-ai/cordis'
import SuperAgentHost from '../lib/index.js'

const dir = mkdtempSync(join(tmpdir(), 'dsh-super-agent-fanout-'))
const ctx = new Context()
await ctx.plugin(SuperAgentHost, {
  dbPath: join(dir, 'events.db'),
  slots: 1,
  assessorMode: 'explicit',
  channelsEnabled: false,
  watchdogSeconds: 0,
})
const host = ctx.superAgent
const now = Math.floor(Date.now() / 1000)

host.ingest({
  id: 'trg-first',
  source: 'local',
  actor: 'human',
  text: '请处理第一件事。',
  threadIds: ['local:fanout'],
  channelIds: ['local:fanout'],
  at: now,
})
await host.tick()
host.ingest({
  id: 'trg-second',
  source: 'local',
  actor: 'human',
  text: '补充：还有第二件事，并入同一工单。',
  threadIds: ['local:fanout'],
  channelIds: ['local:fanout'],
  at: now + 1,
})
await host.tick()

const state = host.state()
const tickets = host.tickets()
const inputs = Object.values(state.inputs)
console.log('tickets:', tickets.length, tickets.map((t) => t.shortName).join(','))
console.log('inputs:', inputs.map((i) => `${i.id}->${i.ticketId}(${i.ref})`).join(','))
console.log('dispositions:', JSON.stringify(state.dispositions ?? {}))

const ok = tickets.length === 1 && inputs.length >= 1
console.log(ok ? 'FANOUT SMOKE OK' : 'FANOUT SMOKE FAIL')
process.exit(ok ? 0 : 1)