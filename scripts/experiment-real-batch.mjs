/**
 * 真实模型批处理实验（文章 §7）：
 * 同一个模型、同一组 4 个线程事件，比较“逐条调用”和“一次批量调用”的
 * 延迟、token 与缓存命中。运行需要 seed.env 里的模型密钥。
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

import { OpenAIClient } from '../src/llm/openai.ts'

const root = join(import.meta.dirname, '..')
const env = Object.fromEntries(
  readFileSync(join(root, 'seed.env'), 'utf8')
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => {
      const at = line.indexOf('=')
      return [line.slice(0, at), line.slice(at + 1)]
    }),
)

const system = [
  'You are a Router. For each thread decide accept|ignore|reply.',
  'Return strict JSON: {"decisions":[{"id":"...","kind":"...","reason":"..."}]}.',
  'Do not use tools. Keep each reason under 20 words.',
  'Stable context: the Super-agent Router batches independent thread events into one model call.',
].join('\n').repeat(20)
const threads = [
  { id: 't1', text: 'Please review the failing login test.' },
  { id: 't2', text: 'Can you summarize the deployment status?' },
  { id: 't3', text: 'Thanks, that is all for now.' },
  { id: 't4', text: 'Fix the typo in README and open a PR.' },
]
const base = {
  baseUrl: env.BAILIAN_BASE_URL,
  apiKey: env.BAILIAN_API_KEY,
  model: 'deepseek-v4.1-flash',
  maxTokens: 512,
  timeoutMs: 120_000,
  maxRetries: 0,
}

async function main() {
  const batchClient = new OpenAIClient(base)
  const batchStarted = performance.now()
  const batchReply = await batchClient.complete([
    { role: 'system', content: system },
    { role: 'user', content: JSON.stringify({ threads }) },
  ])
  const batchMs = Math.round(performance.now() - batchStarted)

  const singleClient = new OpenAIClient(base)
  const singleStarted = performance.now()
  const singleReplies = []
  for (const thread of threads) {
    singleReplies.push(
      await singleClient.complete([
        { role: 'system', content: system },
        { role: 'user', content: JSON.stringify({ threads: [thread] }) },
      ]),
    )
  }
  const singleMs = Math.round(performance.now() - singleStarted)

  const report = {
    at: new Date().toISOString(),
    model: base.model,
    threads: threads.length,
    batch: {
      calls: 1,
      latencyMs: batchMs,
      cache: batchClient.cacheStats(),
      replyChars: batchReply.length,
    },
    single: {
      calls: threads.length,
      latencyMs: singleMs,
      cache: singleClient.cacheStats(),
      replyChars: singleReplies.join('').length,
    },
    speedup: Number((singleMs / Math.max(1, batchMs)).toFixed(2)),
  }
  writeFileSync(join(root, 'docs', 'experiment-batch-real.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify(report, null, 2))
}

await main()