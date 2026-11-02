/**
 * 入站 Source 冒烟：JSONL 收件箱（真实文件轮询）→ Trigger → 工单。
 * 覆盖：轮询、幂等（同一事件不重复触发）、来源状态暴露。
 */
import { appendFileSync, existsSync, mkdtempSync, readFileSync } from 'node:fs'
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

const dir = mkdtempSync(join(tmpdir(), 'dsh-super-agent-sources-'))
const inbox = join(dir, 'inbox.jsonl')
const now = Math.floor(Date.now() / 1000)
appendFileSync(inbox, JSON.stringify({
  id: 'jsonl:1', actor: 'operator', text: '请创建 sources-a.txt',
  threadIds: ['local:sources-a'], channelIds: ['local:sources-a'], at: now,
}) + '\n', 'utf8')

const ctx = new Context()
await ctx.plugin(SuperAgentHost, {
  dbPath: join(dir, 'events.db'),
  slots: 1,
  assessorMode: 'explicit',
  routerMode: 'off',
  channelsEnabled: false,
  watchdogSeconds: 0,
  sourcesEnabled: true,
  sourceJsonlPath: inbox,
  sourceIntervalSeconds: 2,
})
const host = ctx.superAgent

async function waitFor(predicate, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    await new Promise((wait) => setTimeout(wait, 500))
    if (predicate()) return true
  }
  return false
}

const firstSeen = await waitFor(() => host.tickets().length >= 1, 10_000)
console.log('first poll:', firstSeen, 'tickets:', host.tickets().map((ticket) => ticket.threadIds.join('|')).join(','))

appendFileSync(inbox, JSON.stringify({
  id: 'jsonl:2', actor: 'operator', text: '请创建 sources-b.txt',
  threadIds: ['local:sources-b'], channelIds: ['local:sources-b'], at: now + 1,
}) + '\n', 'utf8')
const secondSeen = await waitFor(() => host.tickets().length >= 2, 10_000)
console.log('second poll:', secondSeen, 'tickets:', host.tickets().map((ticket) => ticket.threadIds.join('|')).join(','))

// 幂等：等 3 个轮询周期，同一批事件不应再产生 Trigger。
await new Promise((wait) => setTimeout(wait, 4500))
const triggers = Object.keys(host.state().triggers).length
const snapshot = host.snapshot()
console.log('triggers:', triggers)
console.log('sources:', JSON.stringify(snapshot.sources))

const ok = Boolean(firstSeen && secondSeen && triggers === 2 && snapshot.sources.lastPollAt && snapshot.sources.names.includes('local'))
console.log(ok ? 'SOURCES SMOKE OK' : 'SOURCES SMOKE FAIL')
process.exit(ok ? 0 : 1)