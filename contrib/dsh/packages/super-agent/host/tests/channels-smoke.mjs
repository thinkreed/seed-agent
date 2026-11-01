/**
 * 渠道真机冒烟：真实 DSH runtime worker + 真实飞书群回帖。
 *
 * 地址：`oc_...` 走飞书 im/v1/messages；跑完打印 channels.sent 里服务器返回的 message_id。
 * 需要环境：BAILIAN_API_KEY、FEISHU_APP_ID、FEISHU_APP_SECRET（从 seed-agent/seed.env 读取）。
 */
import { existsSync, mkdirSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

import { Context } from '@deepseek-ai/cordis'
import SuperAgentHost from '../lib/index.js'

const ADDRESS = process.argv[2] ?? 'oc_93f1a464c8258f572ff133db799a2546'
const TEXT = process.argv[3] ?? '请在群里回复一句：渠道联调成功（这是一次自动测试）。'

for (const candidate of ['../seed.env', '../../seed.env', 'seed.env', '../../../seed.env']) {
  const path = resolve(candidate)
  if (!existsSync(path)) continue
  for (const line of readFileSync(path, 'utf8').split(/\r?\n/)) {
    const match = /^(BAILIAN_API_KEY|FEISHU_APP_ID|FEISHU_APP_SECRET)=(.+)$/.exec(line)
    if (match) process.env[match[1]] = match[2].trim()
  }
  if (process.env.BAILIAN_API_KEY) break
}
if (!process.env.BAILIAN_API_KEY) throw new Error('BAILIAN_API_KEY missing')
if (!ADDRESS.startsWith('gh:') && (!process.env.FEISHU_APP_ID || !process.env.FEISHU_APP_SECRET)) {
  throw new Error('feishu credentials missing')
}

const root = mkdtempSync(join(tmpdir(), 'dsh-super-agent-channels-'))
const workspace = join(root, 'work')
const home = join(root, 'home')
mkdirSync(workspace, { recursive: true })
mkdirSync(home, { recursive: true })

const ctx = new Context()
await ctx.plugin(SuperAgentHost, {
  dbPath: join(root, 'events.db'),
  slots: 1,
  assessorMode: 'explicit',
  routerMode: 'off',
  dshBin: resolve('apps/cli/lib/bin.js'),
  dshHome: home,
  dshProfile: 'sdk',
  dshProvider: 'bailian',
  dshModel: 'deepseek-v4.1-flash',
  dshPatch: resolve('config/sdk-bailian.patch.yml'),
  workspace,
  watchdogSeconds: 0,
})

const host = ctx.superAgent
console.log('channel address:', ADDRESS)
host.ingest({
  id: `trg-ch-${Date.now()}`,
  source: 'local',
  actor: 'smoke',
  text: TEXT,
  threadIds: [ADDRESS],
  channelIds: [ADDRESS],
  at: Math.floor(Date.now() / 1000),
})
await host.tick()

const deadline = Date.now() + 300_000
let snapshot
while (Date.now() < deadline) {
  await new Promise((r) => setTimeout(r, 2000))
  snapshot = host.snapshot()
  const sent = snapshot.channels.sent.length
  const ticket = snapshot.tickets[0]
  console.log(`poll: ticket=${ticket ? ticket.state : 'none'} reports=${ticket ? ticket.reports.length : 0} sent=${sent}`)
  if (sent > 0) break
  if (ticket && ticket.reports.length > 0 && ticket.reports.at(-1).status === 'failed') break
}

console.log('tickets:', JSON.stringify(snapshot?.tickets.map((t) => `${t.shortName}:${t.state}`)))
console.log('sent:', JSON.stringify(snapshot?.channels.sent))
const ok = Boolean(snapshot && snapshot.channels.sent.some((m) => m.address === ADDRESS))
console.log(ok ? 'CHANNELS SMOKE OK' : 'CHANNELS SMOKE FAIL')
process.exit(ok ? 0 : 1)