/**
 * 真机：worker 通过 DSH 工具 super_agent_recall 召回（fixture 只存在于召回索引里）。
 * marker 不出现在 worker 提示词中，只能从索引/工具拿到，用来证明召回链路生效。
 */
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
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

const root = mkdtempSync(join(tmpdir(), 'dsh-super-agent-recall-tool-'))
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
const indexPath = host.writeRecallIndex()
const marker = `recall-tool-marker-${Date.now()}`

// fixture：只在索引里放一条 trigger+ticket，worker 的提示词没有 marker。
const index = JSON.parse(readFileSync(indexPath, 'utf8'))
index.triggers['trg-fixture'] = {
  source: 'local', actor: 'fixture', text: `这是只能通过链式召回拿到的上下文：${marker}`,
  threadIds: ['local:fixture'], channelIds: ['local:fixture'], at: Math.floor(Date.now() / 1000),
}
index.threads['local:fixture'] = { triggerIds: ['trg-fixture'], ticketIds: ['tk-fixture'] }
index.tickets['tk-fixture'] = {
  shortName: 't-fixture', state: 'open', threadIds: ['local:fixture'], channelIds: ['local:fixture'],
  triggerId: 'trg-fixture', reports: [],
}
writeFileSync(indexPath, JSON.stringify(index), 'utf8')
console.log('indexPath:', indexPath)

host.ingest({
  id: `trg-recall-tool-${Date.now()}`,
  source: 'local',
  actor: 'smoke',
  text: '用 super_agent_recall 工具：先 kind=ticket、id=tk-fixture 取 handles，再按 handles 里 kind=trigger 的 id 取 text；把最终 text 原样写入 recall-tool.txt。marker 不在提示里，只能用这个工具从召回索引取。',
  threadIds: ['local:recall-tool'],
  channelIds: ['local:recall-tool'],
  at: Math.floor(Date.now() / 1000),
})
await host.tick()
const ticket = host.tickets()[0]
if (!ticket) throw new Error('ticket not created')
console.log('ticket:', ticket.id, 'state:', ticket.state)
// tick 会重写索引；在这里把 fixture 合并进去，worker 的首个工具调用在此之前不会发生。
const latest = JSON.parse(readFileSync(indexPath, 'utf8'))
latest.triggers['trg-fixture'] = index.triggers['trg-fixture']
latest.threads['local:fixture'] = index.threads['local:fixture']
latest.tickets['tk-fixture'] = index.tickets['tk-fixture']
writeFileSync(indexPath, JSON.stringify(latest), 'utf8')

const deadline = Date.now() + 240_000
while (Date.now() < deadline) {
  await new Promise((resolveWait) => setTimeout(resolveWait, 2000))
  if (host.ticket(ticket.id)?.state === 'ended') break
}

const filePath = join(workspace, 'recall-tool.txt')
const written = existsSync(filePath) ? readFileSync(filePath, 'utf8') : ''
console.log('worker output:', JSON.stringify(written.slice(0, 160)))
const ok = written.includes(marker)
console.log(ok ? 'RECALL TOOL SMOKE OK' : 'RECALL TOOL SMOKE FAIL')
process.exit(ok ? 0 : 1)