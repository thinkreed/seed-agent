/** Super-agent host 插件冒烟：cordis 生命周期 + 事件溯源链路 + 看门狗。 */
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { Context } from '@deepseek-ai/cordis'
import SuperAgentHost from '../lib/index.js'

const dir = mkdtempSync(join(tmpdir(), 'dsh-super-agent-'))
const ctx = new Context()
await ctx.plugin(SuperAgentHost, { dbPath: join(dir, 'events.db'), slots: 1, watchdogSeconds: 60, staleSeconds: 1 })

const host = ctx.superAgent
if (!host) throw new Error('service superAgent not mounted')

host.ingest({
  id: 'trg-smoke',
  source: 'local',
  actor: 'smoke',
  text: 'host plugin: mount and create a ticket',
  threadIds: ['local:smoke'],
  channelIds: ['local:smoke'],
  at: Math.floor(Date.now() / 1000),
})
await host.tick()

const tickets = host.tickets()
console.log('store:', host.storePath)
console.log('tickets:', tickets.map((t) => `${t.shortName}:${t.state}`).join(','))
console.log('launched:', host.launched.length)
console.log('replay hash:', host.replayHash().slice(0, 16))
console.log('paused:', host.paused)

// 看门狗：确定性巡检应当安静（刚创建，没有停滞/未投递）。
const watchdog = await host.checkWatchdog()
console.log('watchdog:', watchdog.verdict.action, watchdog.findings.length)
console.log('snapshot watchdog:', JSON.stringify(host.snapshot().watchdog))

const ok = tickets.length === 1 && host.launched.length === 1 && watchdog.verdict.action === 'ok'
console.log(ok ? 'HOST SMOKE OK' : 'HOST SMOKE FAIL')
process.exit(ok ? 0 : 1)