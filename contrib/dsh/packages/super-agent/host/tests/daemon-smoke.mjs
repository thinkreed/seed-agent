/**
 * 存算分离真机：daemon 进程独立保存"真实环境"，worker 通过 super_agent_remote_* 在其上执行。
 * daemon 根目录与工单目录不同——产物出现在 daemon 侧才说明环境真的在外面。
 */
import { existsSync, mkdirSync, mkdtempSync, readFileSync } from 'node:fs'
import { spawn } from 'node:child_process'
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

const root = mkdtempSync(join(tmpdir(), 'dsh-super-agent-daemon-'))
const workspace = join(root, 'work')
const home = join(root, 'home')
const daemonRoot = join(root, 'remote-env')
mkdirSync(workspace, { recursive: true })
mkdirSync(home, { recursive: true })
mkdirSync(daemonRoot, { recursive: true })

// 1) 起一个无状态 daemon 子进程
const token = 'smoke-token'
const daemon = spawn(process.execPath, [resolve('packages/super-agent/daemon/lib/index.js')], {
  env: { ...process.env, SA_DAEMON_ROOT: daemonRoot, SA_DAEMON_TOKEN: token, SA_DAEMON_PORT: '0' },
  stdio: ['ignore', 'pipe', 'pipe'],
})
const port = await new Promise((resolvePort, reject) => {
  let buffer = ''
  const timer = setTimeout(() => reject(new Error('daemon startup timeout')), 15_000)
  daemon.stdout?.on('data', (chunk) => {
    buffer += chunk.toString('utf8')
    for (const line of buffer.split(/\r?\n/)) {
      if (!line.trim()) continue
      try {
        const parsed = JSON.parse(line)
        if (parsed.port) { clearTimeout(timer); resolvePort(parsed.port); return }
      } catch { /* partial line */ }
    }
  })
  daemon.on('error', reject)
})
console.log('daemon port:', port, 'root:', daemonRoot)

// 2) host 只拿 daemon 地址/令牌；状态仍在 host 的 SQLite
const ctx = new Context()
await ctx.plugin(SuperAgentHost, {
  dbPath: join(root, 'events.db'),
  slots: 1,
  assessorMode: 'explicit',
  routerMode: 'off',
  channelsEnabled: false,
  watchdogSeconds: 0,
  sourcesEnabled: false,
  dshBin: resolve('apps/cli/lib/bin.js'),
  dshHome: home,
  dshProfile: 'sdk',
  dshProvider: 'bailian',
  dshModel: 'deepseek-v4.1-flash',
  dshPatch: resolve('config/sdk-bailian.patch.yml'),
  workspace,
  daemonUrl: `http://127.0.0.1:${port}`,
  daemonToken: token,
})
const host = ctx.superAgent
host.ingest({
  id: `trg-daemon-${Date.now()}`,
  source: 'local',
  actor: 'smoke',
  text: [
    '这是存算分离验证：真实环境在 daemon 上，不在你的工单目录。',
    '1) 用 super_agent_remote_write 在 daemon 上写 remote-proof.txt，内容 remote-ok。',
    '2) 用 super_agent_remote_exec 执行 Get-Content remote-proof.txt 验证输出。',
    '3) 报告 daemon 返回的 stdout。',
  ].join('\n'),
  threadIds: ['local:daemon'],
  channelIds: ['local:daemon'],
  at: Math.floor(Date.now() / 1000),
})
await host.tick()
const ticket = host.tickets()[0]
if (!ticket) throw new Error('ticket not created')
const deadline = Date.now() + 240_000
while (Date.now() < deadline) {
  await new Promise((wait) => setTimeout(wait, 2000))
  if (host.ticket(ticket.id)?.state === 'ended') break
}
const proof = join(daemonRoot, 'remote-proof.txt')
const written = existsSync(proof) ? readFileSync(proof, 'utf8').trim() : ''
const ticketDir = join(workspace, 'tickets', ticket.id)
console.log('ticket:', ticket.id, 'state:', host.ticket(ticket.id)?.state)
console.log('daemon file:', JSON.stringify(written), 'exists in daemon root:', existsSync(proof))
console.log('ticket dir leaked file:', existsSync(join(ticketDir, 'remote-proof.txt')))
const ok = Boolean(written === 'remote-ok' && !existsSync(join(ticketDir, 'remote-proof.txt')))
console.log(ok ? 'DAEMON SMOKE OK' : 'DAEMON SMOKE FAIL')
await ctx.fiber.dispose()
daemon.kill()
process.exit(ok ? 0 : 1)