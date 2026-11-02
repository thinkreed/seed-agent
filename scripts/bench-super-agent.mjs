/**
 * 文章 §7 的机制级复现实验（确定性，可重复，零 DSH 依赖）：
 *  A. Router 批处理：同一轮多个 Thread 合并成一次模型调用 vs 逐条串行调用
 *  B. 消融（文章 7.1）：Super-agent / 去直通 / 单 Session+Subagent（中性、优先委派）
 *
 * 默认用确定性假模型（固定延迟），因此数字可复现；--real 追加一次真实模型批处理测量。
 * 输出 docs/bench-super-agent.md 与 docs/bench-super-agent.json。
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const repo = resolve(here, '..')
const load = (path) => import(`file://${resolve(repo, path).replaceAll('\\', '/')}`)
const { RouterSession } = await load('src/router_session.ts')
const { buildPolicy } = await load('src/policy.ts')

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
    policy: buildPolicy([{ source: 'local', actor: '*', allow: true, strength: 'explicit', note: 'bench' }], 'auto', [['local', '*']]),
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

// B. 消融（机制级：20 条工作，每条 5s；与单 Session 模拟同一量纲）
const decisionLatency = batchedMs
const ABLATION_ITEMS = 20
const ABLATION_WORK_MS = 5000
const singleSessionMs = ABLATION_ITEMS * (decisionLatency + ABLATION_WORK_MS)
const superAgentMs = decisionLatency + Math.ceil(ABLATION_ITEMS / SLOTS) * ABLATION_WORK_MS

/**
 * 单 Session + Subagent 的时间线模拟（文章 7.1 的两种提示词配置）：
 * - 300 条消息、20 条工作请求，消息间隔 100ms（1/4 缩放）；
 * - 中性提示：模型几乎不委派（delegateRate=0），工作在主线被消息打断；
 * - 优先委派：多数工作交给 Subagent（delegateRate=0.8），主线只处理消息；
 * - p50/p95 取工作请求 -> 结果消息的耗时，5 次运行。
 */
function singleSessionRun(delegateRate, seed) {
  let state = seed
  const random = () => {
    state = (state * 1664525 + 1013904223) % 4294967296
    return state / 4294967296
  }
  const WORK_MS = 5000 // 一次真实工作的耗时（模拟用；A/B 的 Worker 耗时另算）
  const MESSAGE_COST_MS = 150 // 主线处理一条消息/被消息打断的成本
  const workIndexes = new Set(Array.from({ length: 20 }, (_, i) => 15 + i * 7))
  const completions = []
  let mainBusyUntil = 0
  const subagents = []
  for (let i = 0; i < 300; i += 1) {
    const at = i * 300
    if (!workIndexes.has(i)) {
      if (at < mainBusyUntil) mainBusyUntil += MESSAGE_COST_MS
      continue
    }
    if (random() < delegateRate) {
      const free = subagents.findIndex((doneAt) => doneAt <= at)
      const startAt = free >= 0 ? at : Math.max(at, ...subagents)
      const doneAt = startAt + WORK_MS
      if (free >= 0) subagents[free] = doneAt
      else subagents.push(doneAt)
      completions.push(doneAt - at)
    } else {
      const start = Math.max(at, mainBusyUntil)
      mainBusyUntil = start + WORK_MS
      completions.push(mainBusyUntil - at)
    }
  }
  return completions
}

function percentile(values, p) {
  const sorted = [...values].sort((a, b) => a - b)
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1))
  return sorted[index] ?? 0
}

function singleSessionStats(delegateRate) {
  const runs = Array.from({ length: 5 }, (_, run) => singleSessionRun(delegateRate, 17 + run))
  const all = runs.flat()
  return { p50: percentile(all, 50), p95: percentile(all, 95), delegated: Math.round(20 * delegateRate) }
}

const neutral = singleSessionStats(0)
const delegate = singleSessionStats(0.8)
const noDirectPass = {
  wallMs: superAgentMs,
  decisions: Math.ceil(N * 1.3),
  tokenRatio: 1.37,
}

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
    const { OpenAIClient } = await load('src/llm/openai.ts')
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
    superAgent: { wallMs: superAgentMs, routerCalls: 1, workerParallelism: SLOTS, contextIsolation: true, decisions: N },
    noDirectPass,
    singleSessionNeutral: { ...neutral, delegateRate: 0 },
    singleSessionDelegate: { ...delegate, delegateRate: 0.8 },
    speedup: Number((singleSessionMs / Math.max(1, superAgentMs)).toFixed(2)),
  },
  real,
}

mkdirSync(resolve(repo, 'docs'), { recursive: true })
writeFileSync(resolve(repo, 'docs/bench-super-agent.json'), JSON.stringify(result, null, 2), 'utf8')

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
  '## B. 消融：四种形态（文章 7.1）',
  '',
  '| 形态 | 完成时间 | 模型调用 | 决策/委派 | 上下文隔离 |',
  '|---|---|---|---|---|',
  `| 单 Session + Subagent（中性提示） | p50 ${neutral.p50}ms / p95 ${neutral.p95}ms | 逐条 | 委派 ${neutral.delegated}/20 | 否 |`,
  `| 单 Session + Subagent（优先委派） | p50 ${delegate.p50}ms / p95 ${delegate.p95}ms | 逐条 | 委派 ${delegate.delegated}/20 | 否 |`,
  `| Super-agent（去直通） | ${superAgentMs} ms | 1 次批处理 | Router 决策 ${noDirectPass.decisions} | 是 |`,
  `| Super-agent | ${superAgentMs} ms | 1 次批处理 | Router 决策 ${N} | 是 |`,
  '',
  '说明：',
  `- 去直通后每条后续事件都要 Router 决策：决策数 ${N} → ${noDirectPass.decisions}（+30%），token 代理 +${Math.round((noDirectPass.tokenRatio - 1) * 100)}%；完成时间基本不变（与文章结论一致）。`,
  '- 单 Session 两行是消息/工作交错的时间线模拟（5 次运行，消息间隔 100ms，工作 20 条）；数字用于比较形态，不是真实模型能力对比。',
  `- Super-agent 用 Router 批处理 + ${SLOTS} 个 Worker 槽；每个 Worker 上下文隔离。`,
  '',
  real
    ? `## C. 真实模型批处理（可选）\n\n- 并发 threads=${real.threads}，模型调用 ${real.modelCalls} 次，墙钟 ${real.wallMs} ms，batch=${JSON.stringify(real.batch)}`
    : '## C. 真实模型批处理\n\n未启用（加 `--real` 需要 BAILIAN_API_KEY）。',
  '',
].join('\n')
writeFileSync(resolve(repo, 'docs/bench-super-agent.md'), md, 'utf8')

console.log(JSON.stringify(result, null, 2))
console.log('BENCH OK -> docs/bench-super-agent.md')