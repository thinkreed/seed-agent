/**
 * 全双工：worker 回合进行中再投递一条新指令，不打断当前回合；
 * 回合结束后排队输入立即作为下一轮处理，两条指令都完成。
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

const root = mkdtempSync(join(tmpdir(), 'dsh-super-agent-duplex-'))
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
host.ingest({
  id: `trg-duplex-${Date.now()}`,
  source: 'local',
  actor: 'smoke',
  text: '先执行 pwsh 命令 Start-Sleep -Seconds 8，然后创建 full-duplex-done.txt 内容写 done；完成后报告。',
  threadIds: ['local:duplex'],
  channelIds: ['local:duplex'],
  at: Math.floor(Date.now() / 1000),
})
await host.tick()
const ticket = host.tickets()[0]
if (!ticket) throw new Error('ticket not created')
console.log('ticket:', ticket.id, 'state:', ticket.state)

// 回合进行中（后台 sleep）投递第二条指令：不应并发/丢失，等回合结束处理。
await new Promise((wait) => setTimeout(wait, 2500))
console.log('running? queued before:', host.snapshot().tickets[0]?.queuedInputs)
host.reply(ticket.id, '再创建 full-duplex-second.txt 内容写 second；完成后报告。')

const deadline = Date.now() + 240_000
let current = host.ticket(ticket.id)
while (Date.now() < deadline) {
  await new Promise((wait) => setTimeout(wait, 2000))
  current = host.ticket(ticket.id)
  if (current?.state === 'ended') break
}
const donePath = join(workspace, 'tickets', ticket.id, 'full-duplex-done.txt')
const secondPath = join(workspace, 'tickets', ticket.id, 'full-duplex-second.txt')
const detail = host.snapshot().tickets[0]
console.log('ticket state:', current?.state)
console.log('first file:', existsSync(donePath), 'second file:', existsSync(secondPath))
console.log('queued at end:', detail?.queuedInputs, 'turns:', detail?.turns)
console.log('last prompt:', JSON.stringify(detail?.lastPrompt?.slice(-120)))
console.log('reports:', JSON.stringify(detail?.reports))
// 机制验收：第二轮确实被处理（turns>=2、队列排空、最后 prompt 是第二条指令）。
const ok = Boolean(
  current?.state === 'ended' && (detail?.turns ?? 0) >= 2 && (detail?.queuedInputs ?? 0) === 0 &&
  (detail?.lastPrompt ?? '').includes('full-duplex-second.txt'),
)
console.log(ok ? 'FULL DUPLEX SMOKE OK' : 'FULL DUPLEX SMOKE FAIL')
process.exit(ok ? 0 : 1)