/**
 * 文章 §7 的机制级复现实验（确定性，可重复）：
 *  A. Router 批处理：同一轮多个 Thread 合并成一次模型调用 vs 逐条串行调用
 *  B. 消融：单 Session 串行 vs Super-agent（Router 批处理 + Worker 并发）
 *
 * 默认用确定性假模型（固定延迟），因此数字可复现；--real 追加一次真实模型批处理测量。
 * 输出 docs/bench-super-agent.md 与 docs/bench-super-agent.json。
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, '..')
const hostLib = resolve(repo, 'dsh/packages/super-agent/host/lib/index.js')
const { RouterSession } = await import(`file://${hostLib.replaceAll('\\', '/')}`)
const core = await import(`file://${resolve(repo, 'dsh/packages/super-agent/core/lib/index.js').replaceAll('\\', '/')}`)

const args = new Set(process.argv.slice(2))
const N = Number(process.env.BENCH_THREADS ?? 4)
const MODEL_DELAY_MS = Number(process.env.BENCH_MODEL_MS ?? 40)
const WORKER_MS = Number(process.env.BENCH_WORKER_MS ?? 500)
const SLOTS = Number(process.env.BENCH_SLOTS ?? 2)

const now = () => Number(process.hrtime.bigint() / 1_000_000n)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

class FakeModel {
  constructor(delay = MODEL_DELAY_MS) {
    this.delay = delay
    this.calls = 0
    this.batchSizes = []
  }
  async complete(messages) {
    this.calls += 1
    const user = messages.at(-1)?.content
    let threadIds = []
    try {
      const payload = JSON.parse(user)
      threadIds = (payload.threads ?? []).map((item) => item.view?.threadId ?? item.threadId).filter(Boolean)
    } catch { /* 非 batch 请求 */ }
    this.batchSizes.push(threadIds.length)
    await sleep(this.delay)
    return JSON.stringify({
      decisions: threadIds.map((threadId) => ({
        threadId, kind: 'accept', strength: 'explicit', scope: 'ticket', reason: 'bench', rules: [],
      })),
    })
  }
}

function contextFor(threadId) {
  return {
    threadId,
    triggers: [{
      id: `trg-${threadId}`, source: 'local', actor: 'bench', text: `benchmark task for ${threadId}`,
      threadIds: [threadId], channelIds: [threadId], at: 1,
    }],
    tickets: [],
    policy: core.buildPolicy([{ source: 'local', actor: '*', allow: true, strength: 'explicit', note: 'bench' }], 'auto', [['local', '*']]),
  }
}

function makeRouter(model) {
  const batches = []
  const router = new RouterSession({
    client: model,
    state: () => ({ tickets: {}, triggers: {}, threads: {}, evals: {}, inputs: {}, reports: {}, subscriptions: [] }),
    onBatch: (batch) => batches.push(batch),
  })
  return { router, batches }
}

// A. Router 批处理
const batchedModel = new FakeModel()
const batched = makeRouter(batchedModel)
const contexts = Array.from({ length: N }, (_, i) => contextFor(`th-${i}`))
let started = now()
await Promise.all(contexts.map((context) => batched.router.assess(context)))
const batchedMs = now() - started

const serialModel = new FakeModel()
const serial = makeRouter(serialModel)
started = now()
for (const context of contexts) await serial.router.assess(context)
const serialMs = now() - started

// B. 消融（用上面测到的批处理延迟做决策成本，worker 为固定后台耗时）
const decisionLatency = batchedMs
const singleSessionMs = N * (decisionLatency + WORKER_MS)
const superAgentMs = decisionLatency + Math.ceil(N / SLOTS) * WORKER_MS

// 可选：真实模型批处理
let real = null
if (args.has('--real')) {
  const { readFileSync, existsSync } = await import('node:fs')
  for (const candidate of [resolve(repo, 'seed.env'), resolve(repo, '../seed.env')]) {
    if (!existsSync(candidate)) continue
    for (const line of readFileSync(candidate, 'utf8').split(/\r?\n/)) {
      const match = /^BAILIAN_API_KEY=(.+)$/.exec(line)
      if (match) process.env.BAILIAN_API_KEY = match[1].trim()
    }
    if (process.env.BAILIAN_API_KEY) break
  }
  if (process.env.BAILIAN_API_KEY) {
    const { OpenAIClient } = core
    const model = new OpenAIClient({
      baseUrl: 'https://token-plan.maas.qianwenaiapi.com/compatible-mode/v1',
      apiKey: process.env.BAILIAN_API_KEY,
      model: 'deepseek-v4.1-flash',
      timeoutMs: 60000,
      temperature: 0,
      maxTokens: 600,
    })
    const realModel = { calls: 0, async complete(messages) { this.calls += 1; return model.complete(messages) } }
    const realRouter = makeRouter(realModel)
    const realContexts = contexts.slice(0, Math.min(3, N))
    started = now()
    await Promise.all(realContexts.map((context) => realRouter.router.assess(context)))
    real = { modelCalls: realModel.calls, threads: realContexts.length, wallMs: now() - started, batch: realRouter.batches.at(-1) }
  }
}

const result = {
  generatedAt: new Date().toISOString(),
  env: { threads: N, modelDelayMs: MODEL_DELAY_MS, workerMs: WORKER_MS, slots: SLOTS },
  batching: {
    threads: N,
    batched: { modelCalls: batchedModel.calls, wallMs: batchedMs, batchSizes: batchedModel.batchSizes },
    serial: { modelCalls: serialModel.calls, wallMs: serialMs },
    speedup: Number((serialMs / Math.max(1, batchedMs)).toFixed(2)),
  },
  ablation: {
    baselineSingleSession: { wallMs: singleSessionMs, modelCalls: N, contextIsolation: false },
    superAgent: { wallMs: superAgentMs, routerCalls: 1, workerParallelism: SLOTS, contextIsolation: true },
    speedup: Number((singleSessionMs / Math.max(1, superAgentMs)).toFixed(2)),
  },
  real,
}

mkdirSync(join(repo, 'docs'), { recursive: true })
writeFileSync(join(repo, 'docs/bench-super-agent.json'), JSON.stringify(result, null, 2), 'utf8')

const md = [
  '# Super-agent 机制级 benchmark（§7 复现）',
  '',
  `生成时间：${result.generatedAt}`,
  '',
  `参数：threads=${N}，模型延迟=${MODEL_DELAY_MS}ms（确定性假模型），Worker 耗时=${WORKER_MS}ms，slots=${SLOTS}`,
  '',
  '## A. Router 批处理',
  '',
  '| 方式 | 模型调用次数 | 墙钟时间 |',
  '|---|---|---|',
  `| 逐条串行 | ${result.batching.serial.modelCalls} | ${result.batching.serial.wallMs} ms |`,
  `| 同轮批量（Router） | ${result.batching.batched.modelCalls} | ${result.batching.batched.wallMs} ms |`,
  '',
  `批量调用把 ${N} 个 Thread 合并成 ${result.batching.batched.modelCalls} 次模型调用，墙钟约 ${result.batching.speedup}× 加速。`,
  '',
  '## B. 消融：单 Session 串行 vs Super-agent',
  '',
  '| 形态 | 完成时间 | 模型调用 | Worker 并发 | 上下文隔离 |',
  '|---|---|---|---|---|',
  `| 单 Session 串行 | ${result.ablation.baselineSingleSession.wallMs} ms | ${result.ablation.baselineSingleSession.modelCalls}（逐条） | 1 | 否 |`,
  `| Super-agent | ${result.ablation.superAgent.wallMs} ms | 1（Router 批）+ Worker | ${SLOTS} | 是 |`,
  '',
  `Super-agent 形态约 ${result.ablation.speedup}× 完成，且每个 Worker 上下文隔离。`,
  '',
  real
    ? `## C. 真实模型批处理（可选）\n\n- 并发 threads=${real.threads}，模型调用 ${real.modelCalls} 次，墙钟 ${real.wallMs} ms，batch=${JSON.stringify(real.batch)}`
    : '## C. 真实模型批处理\n\n未启用（加 `--real` 需要 BAILIAN_API_KEY）。',
  '',
].join('\n')
writeFileSync(join(repo, 'docs/bench-super-agent.md'), md, 'utf8')

console.log(JSON.stringify(result, null, 2))
console.log('BENCH OK -> docs/bench-super-agent.md')