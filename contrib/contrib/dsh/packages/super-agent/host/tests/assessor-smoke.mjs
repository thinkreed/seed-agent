/**
 * 两级过滤冒烟：Gate（确定性）之后由真实模型评估 accept/ignore。
 *
 * 期望：闲聊线程不产生工单；明确指令线程产生工单。
 */
import { mkdtempSync, readFileSync, existsSync } from 'node:fs'
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
if (!process.env.BAILIAN_API_KEY) throw new Error('BAILIAN_API_KEY missing')

const dir = mkdtempSync(join(tmpdir(), 'dsh-super-agent-assessor-'))
const ctx = new Context()
await ctx.plugin(SuperAgentHost, {
  dbPath: join(dir, 'events.db'),
  slots: 1,
  assessorMode: 'llm',
  channelsEnabled: false,
  watchdogSeconds: 0,
})
const host = ctx.superAgent
console.log('assessorMode:', host.snapshot().assessorMode)

const now = Math.floor(Date.now() / 1000)
host.ingest({
  id: 'trg-chatter',
  source: 'local',
  actor: 'human',
  text: '今天天气不错，随便聊聊。',
  threadIds: ['local:chatter'],
  channelIds: ['local:chatter'],
  at: now,
})
host.ingest({
  id: 'trg-task',
  source: 'local',
  actor: 'human',
  text: '请在工作目录创建 assessor-check.txt，内容写 ok。',
  threadIds: ['local:task'],
  channelIds: ['local:task'],
  at: now + 1,
})
await host.tick()

const state = host.state()
const evals = Object.values(state.evals).map((item) => ({
  threadId: item.threadId,
  state: item.state,
  kind: item.decision ? item.decision.kind : null,
  reason: item.decision ? item.decision.reason : null,
}))
console.log('evals:', JSON.stringify(evals, null, 1))
const tickets = host.tickets()
console.log('tickets:', JSON.stringify(tickets.map((t) => ({ threadIds: t.threadIds, state: t.state }))))

const taskTicket = tickets.some((t) => t.threadIds.includes('local:task'))
const chatterTicket = tickets.some((t) => t.threadIds.includes('local:chatter'))
const ok = taskTicket && !chatterTicket
console.log(ok ? 'ASSESSOR SMOKE OK' : 'ASSESSOR SMOKE FAIL')
process.exit(ok ? 0 : 1)