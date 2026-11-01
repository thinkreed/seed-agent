/** 真机：Super-agent 工单 -> DSH runtime 回合（真实模型 + 工具）。 */
import { existsSync, mkdirSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

import { Context } from '@deepseek-ai/cordis'
import SuperAgentHost from '../lib/index.js'

// 从 seed-agent/seed.env 取 BAILIAN_API_KEY（DSH 子进程继承 env）。
const candidates = ['../seed.env', '../../seed.env', 'seed.env']
for (const candidate of candidates) {
  const path = resolve(candidate)
  if (!existsSync(path)) continue
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const eq = line.indexOf('=')
    if (eq > 0 && line.slice(0, eq).trim() === 'BAILIAN_API_KEY') {
      process.env.BAILIAN_API_KEY = line.slice(eq + 1).trim()
    }
  }
  if (process.env.BAILIAN_API_KEY) break
}
if (!process.env.BAILIAN_API_KEY) throw new Error('BAILIAN_API_KEY missing')

const root = mkdtempSync(join(tmpdir(), 'dsh-super-agent-sdk-'))
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
})

const host = ctx.superAgent
console.log('usesDshRuntime:', host.usesDshRuntime)
host.ingest({
  id: `trg-sdk-${Date.now()}`,
  source: 'local',
  actor: 'smoke',
  text: '在当前工作目录创建 sdk-hello.txt，内容写：hello from dsh runtime。完成后给出结论。',
  threadIds: ['local:sdk'],
  channelIds: ['local:sdk'],
  at: Math.floor(Date.now() / 1000),
})
await host.tick()

const deadline = Date.now() + 240_000
let ticket
while (Date.now() < deadline) {
  await new Promise((r) => setTimeout(r, 2000))
  ticket = host.tickets()[0]
  if (ticket && ticket.state === 'ended') break
  const report = ticket ? host.state().reports[ticket.id]?.at(-1) : undefined
  if (report && (report.status === 'failed' || report.status === 'blocked')) break
}

const state = host.state()
const reports = ticket ? state.reports[ticket.id] ?? [] : []
console.log('ticket:', ticket ? `${ticket.shortName}:${ticket.state}` : 'none')
console.log('reports:', reports.map((r) => `${r.status}:${r.summary.slice(0, 120)}`).join(' | '))
const output = join(workspace, 'tickets', ticket.id, 'sdk-hello.txt')
console.log('artifact exists:', existsSync(output), existsSync(output) ? readFileSync(output, 'utf8') : '')
console.log('replay hash:', host.replayHash().slice(0, 16))

const ok = Boolean(ticket && ticket.state === 'ended' && reports.some((r) => r.status === 'ready'))
console.log(ok ? 'DSH EXECUTOR SMOKE OK' : 'DSH EXECUTOR SMOKE FAIL')
process.exit(ok ? 0 : 1)