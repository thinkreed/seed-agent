/**
 * Router Session：文章 §2.1 的常驻路由层。
 *
 * 与"单次评估器"的区别：
 * - 常驻：持有跨批次的记忆（memory）与最近对话历史（history），所有判断都在同一个上下文里做。
 * - 批处理：同一轮 tick 内所有 Thread 的 Eval 并发进入 assess()，由这里合并成**一次** LLM 调用。
 * - 可召回：模型可以先返回 {"recall":[...]}，由 host 用 core 的 recall() 取回下一跳，再让它继续决策
 *   （Inline & Spill + 链式召回在 Router 侧的入口）。
 * - 对话：chat() 承接人类交互（面板/IM 的消息进入这里，而不是直接进工单）。
 */

import {
  DEFAULT_BUDGET,
  OpenAIClient,
  assessmentSystemPrompt,
  assessmentUserPrompt,
  buildView,
  recall,
  routerSystemPrompt,
  type AssessContext,
  type Assessor,
  type ContextBudget,
  type Decision,
  type ModelClient,
  type ModelMessage,
  type RecallKind,
  type State,
} from '@deepseek-ai/dsh-super-agent-core'

export interface RouterBatch {
  readonly threads: number
  readonly triggers: number
  readonly at: number
}

export interface RouterOptions {
  readonly client: ModelClient
  readonly state: () => State
  readonly budget?: ContextBudget
  readonly maxSteps?: number
  readonly historyMessages?: number
  readonly memoryChars?: number
  readonly onBatch?: (batch: RouterBatch) => void
}

interface Pending {
  readonly context: AssessContext
  readonly resolve: (decision: Decision) => void
}

const ACCEPT_RULES = [
  'You are also the Router: one persistent context across all threads and channels.',
  'You receive every queued thread in one batch. Decide once per threadId.',
  'Output JSON only: {"decisions":[{"threadId","kind","strength","scope","reason","rules"}]}.',
  'kind is accept | stop | ignore | unavailable. strength is explicit | inferred.',
  'Use ignore for chatter, thanks, status updates, and work already covered by a ticket.',
  'Use stop when a person ends work on the thread.',
  'If deciding needs context that is not inline, first output {"recall":[{"kind":"trigger|thread|ticket","id":"..."}]} and wait for the results.',
].join('\n')

const CHAT_RULES = [
  'You are the Router talking to a person. Answer briefly and concretely (IM-style, <=100 words unless asked for detail).',
  'Output JSON only: {"reply":"..."}.',
].join('\n')

export class RouterSession implements Assessor {
  private readonly client: ModelClient
  private readonly state: () => State
  private readonly budget: ContextBudget
  private readonly maxSteps: number
  private readonly historyMessages: number
  private readonly memoryChars: number
  private readonly onBatch: ((batch: RouterBatch) => void) | undefined
  private readonly pending: Pending[] = []
  private readonly history: ModelMessage[] = []
  private memory = ''
  private scheduled = false
  private lastBatch: RouterBatch | undefined

  constructor(options: RouterOptions) {
    this.client = options.client
    this.state = options.state
    this.budget = options.budget ?? DEFAULT_BUDGET
    this.maxSteps = options.maxSteps ?? 3
    this.historyMessages = options.historyMessages ?? 20
    this.memoryChars = options.memoryChars ?? 2000
    this.onBatch = options.onBatch
  }

  /** 同一轮 tick 内的多个 Thread 请求在这里聚合。 */
  assess(context: AssessContext): Promise<Decision> {
    return new Promise<Decision>((resolve) => {
      this.pending.push({ context, resolve })
      this.schedule()
    })
  }

  /** 人类消息进入 Router（面板/IM 对话）。 */
  async chat(text: string): Promise<string> {
    const state = this.state()
    const tickets = Object.values(state.tickets)
      .sort((a, b) => a.id.localeCompare(b.id))
      .slice(-20)
      .map((ticket) => ({
        id: ticket.id,
        shortName: ticket.shortName,
        state: ticket.state,
        threadIds: ticket.threadIds,
        channelIds: ticket.channelIds,
      }))
    const messages: ModelMessage[] = [
      { role: 'system', content: `${routerSystemPrompt()}\n\n${CHAT_RULES}\n\nMemory:\n${this.memory || '(empty)'}` },
      ...this.history.slice(-this.historyMessages),
      { role: 'user', content: JSON.stringify({ chat: text, tickets }) },
    ]
    const raw = await this.client.complete(messages)
    const reply = parseChatReply(raw)
    this.remember(`person: ${text}\nrouter: ${reply}`)
    this.history.push({ role: 'user', content: JSON.stringify({ chat: text }) })
    this.history.push({ role: 'assistant', content: JSON.stringify({ reply }) })
    this.trimHistory()
    return reply
  }

  snapshot(): { readonly memory: string; readonly history: number; readonly lastBatch: RouterBatch | undefined } {
    return { memory: this.memory, history: this.history.length, lastBatch: this.lastBatch }
  }

  private schedule(): void {
    if (this.scheduled) return
    this.scheduled = true
    setImmediate(() => {
      void this.flush()
    })
  }

  private async flush(): Promise<void> {
    this.scheduled = false
    const batch = this.pending.splice(0)
    if (batch.length === 0) return
    const views = batch.map((item) => buildView(item.context, this.budget))
    const info: RouterBatch = {
      threads: views.length,
      triggers: views.reduce((total, view) => total + view.triggers.length, 0),
      at: Math.floor(Date.now() / 1000),
    }
    this.lastBatch = info
    this.onBatch?.(info)

    let decisions: Map<string, Decision>
    try {
      decisions = await this.decide(views)
    } catch (error) {
      // 评估失败不阻塞工单：按 ignore 放行，并把原因记进记忆，下一批可见。
      const reason = String(error).slice(0, 200)
      this.remember(`decision-error: ${reason}`)
      decisions = new Map(views.map((view) => [view.threadId, ignored(reason)]))
    }
    for (const item of batch) {
      const decision = decisions.get(item.context.threadId) ?? ignored('router-no-decision')
      item.resolve(decision)
    }
    this.remember(
      `batch threads=${info.threads} triggers=${info.triggers} → ` +
        [...decisions.entries()].map(([threadId, decision]) => `${threadId}:${decision.kind}`).join(','),
    )
  }

  private async decide(views: ReturnType<typeof buildView>[]): Promise<Map<string, Decision>> {
    const messages: ModelMessage[] = [
      {
        role: 'system',
        content: `${routerSystemPrompt()}\n\n${ACCEPT_RULES}\n\nMemory:\n${this.memory || '(empty)'}`,
      },
      ...this.history.slice(-this.historyMessages),
      { role: 'user', content: JSON.stringify({ threads: views.map((view) => ({ view, assessment: assessmentSystemPrompt(), context: assessmentUserPrompt(view) })) }) },
    ]
    for (let step = 0; step < this.maxSteps; step += 1) {
      const raw = await this.client.complete(messages)
      const payload = parsePayload(raw)
      if (!payload) return new Map(views.map((view) => [view.threadId, ignored('router-unparsable')]))

      const recalls = readRecalls(payload)
      if (recalls.length > 0) {
        const results = recalls.map((request) => recall(this.state(), request.kind, request.id, this.budget))
        messages.push({ role: 'assistant', content: raw })
        messages.push({ role: 'user', content: JSON.stringify({ recallResults: results }) })
        continue
      }

      const decisions = readDecisions(payload)
      if (decisions.size > 0) return decisions
      if (typeof payload.kind === 'string') {
        // 单条决策：应用到本批所有 Thread。
        const single = decisionOf(payload)
        return new Map(views.map((view) => [view.threadId, single]))
      }
      return new Map(views.map((view) => [view.threadId, ignored('router-empty')]))
    }
    return new Map(views.map((view) => [view.threadId, ignored('router-step-limit')]))
  }

  private remember(line: string): void {
    const next = `${this.memory}\n${line}`.trim()
    this.memory = next.length > this.memoryChars ? next.slice(-this.memoryChars) : next
  }

  private trimHistory(): void {
    const limit = this.historyMessages
    if (this.history.length > limit * 2) this.history.splice(0, this.history.length - limit * 2)
  }
}

/** 用环境变量构造 OpenAI 兼容客户端的便捷工厂。 */
export function createRouterClient(options: {
  baseUrl: string
  apiKey: string
  model: string
  timeoutMs: number
}): ModelClient {
  return new OpenAIClient({
    baseUrl: options.baseUrl,
    apiKey: options.apiKey,
    model: options.model,
    timeoutMs: options.timeoutMs,
    temperature: 0,
    maxTokens: 1200,
  })
}

function ignored(reason: string): Decision {
  return { kind: 'ignore', strength: 'inferred', reason, scope: 'ticket', rules: [] }
}

function parsePayload(raw: string): Record<string, unknown> | undefined {
  const start = raw.indexOf('{')
  const end = raw.lastIndexOf('}')
  if (start < 0 || end <= start) return undefined
  try {
    const parsed: unknown = JSON.parse(raw.slice(start, end + 1))
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : undefined
  } catch {
    return undefined
  }
}

function readRecalls(payload: Record<string, unknown>): { kind: RecallKind; id: string }[] {
  const raw = payload.recall
  if (!Array.isArray(raw)) return []
  const kinds: readonly RecallKind[] = ['trigger', 'thread', 'ticket']
  return raw.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const record = item as Record<string, unknown>
    const kind = typeof record.kind === 'string' && kinds.includes(record.kind as RecallKind) ? (record.kind as RecallKind) : undefined
    const id = typeof record.id === 'string' ? record.id : undefined
    return kind && id ? [{ kind, id }] : []
  })
}

function readDecisions(payload: Record<string, unknown>): Map<string, Decision> {
  const raw = payload.decisions
  const map = new Map<string, Decision>()
  if (!Array.isArray(raw)) return map
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const record = item as Record<string, unknown>
    const threadId = typeof record.threadId === 'string' ? record.threadId : undefined
    if (!threadId) continue
    map.set(threadId, decisionOf(record))
  }
  return map
}

function decisionOf(record: Record<string, unknown>): Decision {
  const kind = record.kind
  if (kind !== 'accept' && kind !== 'stop' && kind !== 'ignore' && kind !== 'unavailable') return ignored('bad-kind')
  const strength = record.strength === 'explicit' ? 'explicit' : 'inferred'
  const reason = typeof record.reason === 'string' ? record.reason.slice(0, 300) : ''
  const scope = typeof record.scope === 'string' && record.scope ? record.scope : 'ticket'
  const rules = Array.isArray(record.rules)
    ? record.rules.filter((entry): entry is string => typeof entry === 'string').slice(0, 10)
    : []
  return { kind, strength, reason, scope, rules }
}

function parseChatReply(raw: string): string {
  const payload = parsePayload(raw)
  if (payload && typeof payload.reply === 'string' && payload.reply.trim()) return payload.reply.trim()
  return raw.trim()
}