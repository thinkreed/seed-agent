/**
 * Watchdog 独立 session 裁定：确定性 findings 交给主系统之外的 DSH runtime 会话，
 * 由该会话在独立工作目录（<workspace>/.seed/watchdog）里判断是否介入。
 */
import { existsSync, mkdirSync, mkdtempSync, readFileSync } from 'node:fs'
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

const root = mkdtempSync(join(tmpdir(), 'dsh-super-agent-watchdog-session-'))
const workspace = join(root, 'work')
const home = join(root, 'home')
mkdirSync(workspace, { recursive: true })
mkdirSync(home, { recursive: true })

const ctx = new Context()
await ctx.plugin(SuperAgentHost, {
  dbPath: join(root, 'events.db'),
  slots: 1,
  dshBin: resolve('apps/cli/lib/bin.js'),
  dshHome: home,
  dshProfile: 'sdk',
  dshProvider: 'bailian',
  dshModel: 'deepseek-v4.1-flash',
  dshPatch: resolve('config/sdk-bailian.patch.yml'),
  workspace,
  assessorMode: 'explicit',
  routerMode: 'off',
  channelsEnabled: false,
  watchdogSeconds: 0,
  watchdogMode: 'session',
  staleSeconds: 1,
  sourcesEnabled: false,
})
const host = ctx.superAgent
host.ingest({
  id: 'trg-watchdog-session',
  source: 'local',
  actor: 'human',
  text: 'Create a ticket that never completes: no executor will report back.',
  threadIds: ['local:watchdog-session'],
  channelIds: ['local:watchdog-session'],
  at: Math.floor(Date.now() / 1000),
})
await host.tick()
await new Promise((wait) => setTimeout(wait, 2600))

const report = await host.checkWatchdog()
const snapshot = host.snapshot()
const sessionDir = join(workspace, '.seed', 'watchdog')
console.log('findings:', report.findings.map((finding) => `${finding.kind}:${finding.ticketId}`).join(','))
console.log('verdict:', JSON.stringify(report.verdict))
console.log('session dir exists:', existsSync(sessionDir))
console.log('snapshot watchdog:', JSON.stringify(snapshot.watchdog))

const ok = Boolean(
  report.findings.length >= 1 &&
  report.verdict.reason.length > 0 &&
  (report.verdict.action === 'ok' || report.verdict.action === 'intervene') &&
  existsSync(sessionDir) &&
  (snapshot.watchdog?.interventions?.length ?? 0) >= 1 &&
  snapshot.config?.watchdogMode === 'session',
)
console.log(ok ? 'WATCHDOG SESSION SMOKE OK' : 'WATCHDOG SESSION SMOKE FAIL')
await ctx.fiber.dispose()
process.exit(ok ? 0 : 1)