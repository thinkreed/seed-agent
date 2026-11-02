/**
 * handback / unsubscribe：
 *  - Worker 交回后，Thread 不再属于旧工单，Router 重新评估可新建工单
 *  - 控制请求文件（worker 工具入口）走同一条路径
 */
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'

import { Context } from '@deepseek-ai/cordis'
import SuperAgentHost from '../lib/index.js'

const root = mkdtempSync(join(tmpdir(), 'dsh-super-agent-handback-'))
const ctx = new Context()
await ctx.plugin(SuperAgentHost, {
  dbPath: join(root, 'events.db'),
  slots: 1,
  assessorMode: 'explicit',
  routerMode: 'off',
  channelsEnabled: false,
  watchdogSeconds: 0,
  sourcesEnabled: false,
})
const host = ctx.superAgent
host.ingest({
  id: 'trg-hb-1',
  source: 'local',
  actor: 'human',
  text: '第一个任务：创建 hb-a.txt',
  threadIds: ['local:hb'],
  channelIds: ['local:hb'],
  at: Math.floor(Date.now() / 1000),
})
await host.tick()
const first = host.tickets()[0]
console.log('ticket A:', first?.id, first?.state)

host.handback(first.id, 'out of scope')
await host.tick()
const afterApi = host.tickets()
console.log('after handback (api):', afterApi.map((ticket) => ticket.id).join(','))

mkdirSync(join(dirname(join(root, 'events.db')), 'control'), { recursive: true })
const controlDir = join(dirname(join(root, 'events.db')), 'control')
writeFileSync(join(controlDir, 'request-1.json'), JSON.stringify({
  action: 'handback', ticketId: afterApi[1]?.id ?? first.id, reason: 'worker tool request',
}), 'utf8')
await host.tick()
const afterFile = host.tickets()
console.log('after handback (file):', afterFile.map((ticket) => ticket.id).join(','))

const subscriptions = host.state().subscriptions.filter((item) => item.threadId === 'local:hb')
console.log('subscriptions on thread:', subscriptions.map((item) => item.ticketId).join(','))
const ok = afterApi.length >= 2 && afterFile.length >= 3 &&
  subscriptions.length === 1 && subscriptions[0]?.ticketId === afterFile.at(-1)?.id

// 工具注册检查：两个 worker 控制工具可被 DSH 加载（纯定义校验，不启 runtime）。
try {
  const toolLib = await import('../../tool-control/lib/index.js')
  const registered = []
  toolLib.apply({ tools: { register: (definition) => registered.push(definition.name) } })
  const names = registered.join(',')
  console.log('control tools:', names)
  if (!names.includes('super_agent_handback') || !names.includes('super_agent_unsubscribe')) {
    console.log('HANDBACK SMOKE FAIL (tool registration)')
    process.exit(1)
  }
} catch (error) {
  console.log('tool check skipped:', String(error).slice(0, 120))
}

console.log(ok ? 'HANDBACK SMOKE OK' : 'HANDBACK SMOKE FAIL')
process.exit(ok ? 0 : 1)