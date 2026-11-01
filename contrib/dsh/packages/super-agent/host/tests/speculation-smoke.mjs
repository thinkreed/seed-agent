/**
 * 投机执行：后台尝试，有价值才交付（deliver=true → 发 channel），无价值静默丢弃。
 * 两个样本分别要求 deliver=true / false，验证判定与交付路径。
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

const root = mkdtempSync(join(tmpdir(), 'dsh-super-agent-spec-'))
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
  channelsEnabled: true,
  watchdogSeconds: 0,
  sourcesEnabled: false,
  speculationEnabled: true,
})
const host = ctx.superAgent

const delivered = await host.speculate(
  '群反馈：需要一个可直接落地的小修复。请立即在当前工作目录创建 spec-deliver.txt（内容写 ok）并确认文件存在；这是一个可交付的结果，最终输出 {"deliver":true,"summary":"已创建 spec-deliver.txt 并验证存在"}。',
  ['local:spec'],
)
console.log('case1:', JSON.stringify(delivered))

const discarded = await host.speculate(
  '群聊里只是有人说"今天天气不错"。此案例无价值，必须静默丢弃：最终请输出 {"deliver":false,"summary":"无关闲聊，不交付"}。',
  [],
)
console.log('case2:', JSON.stringify(discarded))

const snapshot = host.snapshot()
console.log('speculations:', JSON.stringify(snapshot.speculations))
const sent = snapshot.channels?.sent ?? []
console.log('channel sent:', JSON.stringify(sent))
const ok = Boolean(
  delivered.delivered === true && delivered.summary.length > 0 &&
  sent.some((message) => message.address === 'local:spec') &&
  discarded.delivered === false &&
  snapshot.speculations.length === 2,
)
console.log(ok ? 'SPECULATION SMOKE OK' : 'SPECULATION SMOKE FAIL')
await ctx.fiber.dispose()
process.exit(ok ? 0 : 1)