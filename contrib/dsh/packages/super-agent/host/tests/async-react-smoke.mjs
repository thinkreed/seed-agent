/**
 * 异步 ReAct：worker 用 super_agent_start 启动后台命令后立即继续（Started 不再阻塞），
 * 期间创建前台文件，再用 super_agent_status 轮询到 done，最后两个文件都应在。
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

const root = mkdtempSync(join(tmpdir(), 'dsh-super-agent-async-'))
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
  id: `trg-async-${Date.now()}`,
  source: 'local',
  actor: 'smoke',
  text: [
    '严格按步骤：',
    '1) 调用 super_agent_start，command 为：Start-Sleep -Seconds 6; Set-Content async-done.txt done',
    '2) start 立即返回 jobId 后，不要等待，马上用写文件工具创建 async-foreground.txt，内容 fg',
    '3) 之后每 2 秒调用一次 super_agent_status(jobId)，直到 status=done',
    '4) 确认 async-done.txt 存在；报告 jobId 和两个文件。不要在前台自己创建 async-done.txt；如果后台命令失败就报告失败。',
  ].join('\n'),
  threadIds: ['local:async'],
  channelIds: ['local:async'],
  at: Math.floor(Date.now() / 1000),
})
await host.tick()
const ticket = host.tickets()[0]
if (!ticket) throw new Error('ticket not created')
console.log('ticket:', ticket.id, 'state:', ticket.state)

const deadline = Date.now() + 240_000
let current = host.ticket(ticket.id)
while (Date.now() < deadline) {
  await new Promise((wait) => setTimeout(wait, 2000))
  current = host.ticket(ticket.id)
  if (current?.state === 'ended') break
}
const donePath = join(workspace, 'async-done.txt')
const foregroundPath = join(workspace, 'async-foreground.txt')
console.log('ticket state:', current?.state)
console.log('done file:', existsSync(donePath), 'foreground file:', existsSync(foregroundPath))
const ok = Boolean(current?.state === 'ended' && existsSync(donePath) && existsSync(foregroundPath))
console.log(ok ? 'ASYNC REACT SMOKE OK' : 'ASYNC REACT SMOKE FAIL')
process.exit(ok ? 0 : 1)