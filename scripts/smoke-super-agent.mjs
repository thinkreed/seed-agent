/**
 * Super-agent core 冒烟：在 DSH fork 里加载 @deepseek-ai/dsh-super-agent-core 的构建产物，
 * 跑一遍事件溯源链路（ingest -> eval -> ticket -> assignment），确认包可用。
 *
 * 运行：node scripts/smoke-super-agent.mjs
 */
import { Runtime, SeqIds, defaultPolicy } from '../dsh/packages/super-agent/core/lib/index.js'

const clock = { now: () => 1_700_000_000 }
const ids = new SeqIds()

const assessor = {
  async assess() {
    return { kind: 'accept', strength: 'explicit', reason: 'smoke', rules: [], scope: 'ticket' }
  },
}

const executor = {
  launched: [],
  async launch(assignment, ticket) {
    this.launched.push({ assignment, ticket })
  },
  async deliver() {},
  async stop() {},
}

const runtime = Runtime.build({
  assessor,
  executor,
  clock,
  ids,
  config: { policy: defaultPolicy(), slots: 1 },
})

runtime.engine.ingest({
  id: 'trg-smoke',
  source: 'local',
  actor: 'smoke',
  text: 'smoke: write a file',
  threadIds: ['local:smoke'],
  channelIds: ['local:smoke'],
  at: 1_700_000_000,
})

await runtime.tickUntilIdle()
const state = runtime.engine.state
const tickets = Object.values(state.tickets)
const assignments = Object.values(state.assignments)

console.log('events:', runtime.store.lastSeq())
console.log('tickets:', tickets.map((t) => `${t.shortName}:${t.state}`).join(','))
console.log('assignments:', assignments.map((a) => `${a.id}:${a.state}`).join(','))
console.log('launched:', executor.launched.length)
console.log('replay hash:', runtime.store.replayHash().slice(0, 16))

const ok = tickets.length === 1 && assignments.length === 1 && executor.launched.length === 1
console.log(ok ? 'CORE SMOKE OK' : 'CORE SMOKE FAIL')
runtime.close()
process.exit(ok ? 0 : 1)