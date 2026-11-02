/**
 * Watchdog 模型裁定：确定性 findings（停滞）交给独立模型判断是否介入；
 * 介入时记录 intervention、retry 工单并安排复查。
 */
import { existsSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

import { Context } from '@deepseek-ai/cordis'
import SuperAgentHost from '../lib/index.js'

for (const candidate of ['../seed.env', '../../seed.env', 'seed.env']) {
  const path = resolve(candidate)
  if (!existsSync(path)) continue
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const eq = line.indexOf('=')
    if (eq > 0 && line.slice(0, eq).trim() === 'BAILIAN_API_KEY') process.env.BAILIAN_API_KEY = line.slice(eq + 1).trim()
  }
  if (process.env.BAILIAN_API_KEY) break
}
if (!process.env.BAILIAN_API_KEY) throw new Error('BAILIAN_API_KEY missing')

const root = mkdtempSync(join(tmpdir(), 'dsh-super-agent-watchdog-'))
const ctx = new Context()
await ctx.plugin(SuperAgentHost, {
  dbPath: join(root, 'events.db'),
  slots: 1,
  assessorMode: 'explicit',
  routerMode: 'off',
  channelsEnabled: false,
  watchdogSeconds: 0,
  watchdogMode: 'llm',
  staleSeconds: 1,
  sourcesEnabled: false,
})
const host = ctx.superAgent
host.ingest({
  id: 'trg-watchdog',
  source: 'local',
  actor: 'human',
  text: '创建一个永远不完成的工单（pending executor 不会回报）',
  threadIds: ['local:watchdog'],
  channelIds: ['local:watchdog'],
  at: Math.floor(Date.now() / 1000),
})
await host.tick()
await new Promise((wait) => setTimeout(wait, 2600))

const report = await host.checkWatchdog()
const snapshot = host.snapshot()
console.log('findings:', report.findings.map((finding) => `${finding.kind}:${finding.ticketId}`).join(','))
console.log('verdict:', JSON.stringify(report.verdict))
console.log('snapshot watchdog:', JSON.stringify(snapshot.watchdog))

// 对照组：同一状态交给确定性模式 → 直接 intervene；模型模式可能判 ok（避免误报）。
const ctx2 = new Context()
await ctx2.plugin(SuperAgentHost, {
  dbPath: join(root, 'events2.db'),
  slots: 1,
  assessorMode: 'explicit',
  routerMode: 'off',
  channelsEnabled: false,
  watchdogSeconds: 0,
  watchdogMode: 'deterministic',
  staleSeconds: 1,
  sourcesEnabled: false,
})
const host2 = ctx2.superAgent
host2.ingest({
  id: 'trg-watchdog-2',
  source: 'local',
  actor: 'human',
  text: '同样不完成的工单（确定性对照组）',
  threadIds: ['local:watchdog-2'],
  channelIds: ['local:watchdog-2'],
  at: Math.floor(Date.now() / 1000),
})
await host2.tick()
await new Promise((wait) => setTimeout(wait, 1600))
const deterministic = await host2.checkWatchdog()
const snapshot2 = host2.snapshot()
console.log('deterministic:', JSON.stringify(deterministic.verdict), 'rechecks:', snapshot2.watchdog?.rechecks)

const modelJudged = report.verdict.reason !== 'deterministic-findings'
const ok = Boolean(
  report.findings.length >= 1 && report.verdict.reason.length > 0 &&
  (report.verdict.action === 'ok' || report.verdict.action === 'intervene') &&
  (snapshot.watchdog?.interventions?.length ?? 0) >= 1 &&
  deterministic.verdict.action === 'intervene' && modelJudged,
)
console.log(ok ? 'WATCHDOG LLM SMOKE OK' : 'WATCHDOG LLM SMOKE FAIL')
await ctx2.fiber.dispose()
await ctx.fiber.dispose()
process.exit(ok ? 0 : 1)