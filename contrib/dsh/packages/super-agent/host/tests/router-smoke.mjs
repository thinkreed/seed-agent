/**
 * Router Session 冒烟：
 *  - 两个不同 Thread 的 Trigger 在同一 tick 内被合并成一次 Router LLM 调用（批处理）
 *  - 明确指令建单、闲聊不建单（语义层决定）
 *  - 对话（chat）由 Router 回复并写入记忆
 */
import { existsSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

import { Context } from '@deepseek-ai/cordis'
import SuperAgentHost from '../lib/index.js'

for (const candidate of ['../seed.env', '../../seed.env', 'seed.env', '../../../seed.env']) {
  const path = resolve(candidate)
  if (!existsSync(path)) continue
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const match = /^(BAILIAN_API_KEY)=(.+)$/.exec(line)
    if (match) process.env[match[1]] = match[2].trim()
  }
  if (process.env.BAILIAN_API_KEY) break
}
if (!process.env.BAILIAN_API_KEY) throw new Error('BAILIAN_API_KEY missing')

const dir = mkdtempSync(join(tmpdir(), 'dsh-super-agent-router-'))
const ctx = new Context()
await ctx.plugin(SuperAgentHost, {
  dbPath: join(dir, 'events.db'),
  slots: 1,
  assessorMode: 'llm',
  routerMode: 'llm',
  channelsEnabled: false,
  watchdogSeconds: 0,
})
const host = ctx.superAgent
const now = Math.floor(Date.now() / 1000)

host.ingest({
  id: 'trg-task',
  source: 'local',
  actor: 'human',
  text: '请在工作目录创建 router-check.txt，内容写 routed。',
  threadIds: ['local:task'],
  channelIds: ['local:task'],
  at: now,
})
host.ingest({
  id: 'trg-chatter',
  source: 'local',
  actor: 'human',
  text: '今天天气不错，随便聊聊。',
  threadIds: ['local:chatter'],
  channelIds: ['local:chatter'],
  at: now + 1,
})
await host.tick()

const snapshot = host.snapshot()
const batch = snapshot.router.lastBatch
console.log('router mode:', snapshot.router.mode)
console.log('lastBatch:', JSON.stringify(batch))
console.log('tickets:', JSON.stringify(host.tickets().map((ticket) => ({ threads: ticket.threadIds, state: ticket.state }))))

const chatResult = await host.command({ action: 'chat', text: '现在有几个工单？一句话回答。' })
console.log('chat reply:', chatResult.reply)
console.log('router memory chars:', chatResult.router.memory.length, 'history:', chatResult.router.history)

const taskTicket = host.tickets().some((ticket) => ticket.threadIds.includes('local:task'))
const chatterTicket = host.tickets().some((ticket) => ticket.threadIds.includes('local:chatter'))
const ok = Boolean(
  batch && batch.threads === 2 && batch.triggers === 2 &&
  taskTicket && !chatterTicket &&
  typeof chatResult.reply === 'string' && chatResult.reply.length > 0 &&
  chatResult.router.history > 0,
)
console.log(ok ? 'ROUTER SMOKE OK' : 'ROUTER SMOKE FAIL')
process.exit(ok ? 0 : 1)