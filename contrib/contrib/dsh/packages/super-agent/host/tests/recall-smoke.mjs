/** 链式召回：召回索引文件 + 逐跳 handles（trigger → thread → ticket）。 */
import { existsSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { Context } from '@deepseek-ai/cordis'
import SuperAgentHost from '../lib/index.js'

const dir = mkdtempSync(join(tmpdir(), 'dsh-super-agent-recall-'))
const ctx = new Context()
await ctx.plugin(SuperAgentHost, {
  dbPath: join(dir, 'events.db'),
  slots: 1,
  assessorMode: 'explicit',
  routerMode: 'off',
  channelsEnabled: false,
  watchdogSeconds: 0,
  sourcesEnabled: false,
})
const host = ctx.superAgent
const now = Math.floor(Date.now() / 1000)
host.ingest({
  id: 'trg-recall',
  source: 'local',
  actor: 'human',
  text: '请创建 recall-check.txt，并记录一次可追溯的操作。',
  threadIds: ['local:recall'],
  channelIds: ['local:recall'],
  at: now,
})
await host.tick()

const indexPath = host.writeRecallIndex()
const index = JSON.parse(readFileSync(indexPath, 'utf8'))
const trigger = index.triggers['trg-recall']
const ticketId = Object.keys(index.tickets)[0]
const thread = index.threads['local:recall']
console.log('index:', indexPath, 'triggers:', Object.keys(index.triggers).length, 'tickets:', Object.keys(index.tickets).length)
console.log('thread entry:', JSON.stringify(thread))

const hop1 = host.recallContext('trigger', 'trg-recall')
const hop2 = host.recallContext('thread', 'local:recall')
const hop3 = host.recallContext('ticket', ticketId)
console.log('trigger handles:', JSON.stringify(hop1.handles))
console.log('thread handles:', JSON.stringify(hop2.handles))
console.log('ticket summary:', hop3.summary)

const ok = Boolean(
  existsSync(indexPath) && trigger && thread && thread.ticketIds.includes(ticketId) &&
  hop1.handles.some((handle) => handle.kind === 'thread' && handle.id === 'local:recall') &&
  hop2.handles.some((handle) => handle.kind === 'ticket' && handle.id === ticketId) &&
  hop3.found,
)
console.log(ok ? 'RECALL SMOKE OK' : 'RECALL SMOKE FAIL')
process.exit(ok ? 0 : 1)