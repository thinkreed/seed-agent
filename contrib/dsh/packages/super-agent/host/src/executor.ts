/**
 * DSH SDK 执行器：把一个 Assignment 变成一个真实的 DSH session 回合。
 *
 * 走官方 @deepseek-ai/dsh-sdk-client：`DeepSeekHarness.run(prompt)` 会拉起一个
 * DSH runtime 子进程（真实模型 + 工具 + 沙箱），返回该回合的最终文本。
 * 每次执行对应一个 session；同一工单的后续投递复用该 sessionId。
 *
 * 这是「存算分离」的计算侧：状态仍在 Super-agent 事件库，执行在 DSH runtime。
 */

import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import type { DeepSeekHarnessOptions, RunResult } from '@deepseek-ai/dsh-sdk-client'
import { DeepSeekHarness } from '@deepseek-ai/dsh-sdk-client'
import type { Assignment, Clock, Executor, Input, Report, ReportStatus, Ticket, Trigger } from '@deepseek-ai/dsh-super-agent-core'

export interface DshSessionLike {
  run(prompt: string): Promise<RunResult>
}

export interface DshHarnessLike {
  session(sessionId?: string): DshSessionLike
  resumeSession(sessionId: string): Promise<DshSessionLike>
  close(): Promise<void>
}

export interface SdkDshExecutorOptions {
  /** 传给 SDK 的启动配置（dshBin / dshHome / profile / provider / model…）。 */
  readonly harness: DeepSeekHarnessOptions
  /** 离线契约测试注入；生产缺省使用真实 DeepSeekHarness。 */
  readonly harnessFactory?: (options: DeepSeekHarnessOptions) => DshHarnessLike
  /** sessionId 持久化路径；host 重启后复用 DSH session。 */
  readonly sessionStorePath?: string
  /** 报告正文上限（默认 20000；不再按 600 截断）。 */
  readonly maxSummaryChars?: number
  /** worker 的工作目录。 */
  readonly workspace?: string
  readonly clock: Clock
  /** 把结果写回引擎（engine.report）。 */
  readonly onReport: (report: Report) => void
  /** 取工单的原始指令文本（source trigger / inputs）。 */
  readonly describeTicket?: (ticketId: string) => string
  /** 观察每次真正发给 DSH worker 的提示词（验收/调试）。 */
  readonly onPrompt?: (ticketId: string, prompt: string) => void
  /** Inline & Spill：指令超过该字符数就落盘，prompt 里只留摘要 + 文件路径。 */
  readonly spillChars?: number
  /** 落盘目录（默认 workspace/.seed/spills）。 */
  readonly spillDir?: string
  /** 召回索引文件：worker 可用读取工具按 id 逐跳展开上下文。 */
  readonly recallIndexPath?: string
  /** 每工单独立工作目录（文章 §3.3/执行语义：工单产物隔离）。 */
  readonly ticketDir?: (ticket: Ticket) => string
}

/** 落盘后的指令：inline 是写进 prompt 的摘要，spillPath 供 worker 链式召回。 */
export interface SpilledInstruction {
  readonly inline: string
  readonly spillPath?: string
}

/** 超过预算的上下文落盘，worker 需要细节时按路径读取（链式召回的第一跳）。 */
export function spillInstruction(
  ticket: Ticket,
  instruction: string,
  options: { threshold: number; dir: string },
): SpilledInstruction {
  const text = instruction.trim()
  if (text.length <= options.threshold) return { inline: text }
  mkdirSync(options.dir, { recursive: true })
  const spillPath = join(options.dir, `${ticket.shortName}.txt`)
  writeFileSync(spillPath, text, 'utf8')
  const head = text.slice(0, Math.min(600, options.threshold))
  return {
    inline: `${head}\n\n…（原始上下文共 ${text.length} 字符，已落盘：${spillPath}；需要细节时用读取工具打开它。）`,
    spillPath,
  }
}

export class SdkDshExecutor implements Executor {
  private readonly harnessByTicket = new Map<string, DshHarnessLike>()
  private readonly options: SdkDshExecutorOptions
  private readonly sessionByTicket = new Map<string, string>()
  private readonly assignmentByTicket = new Map<string, string>()
  /** 全双工：正在跑的工单，以及回合期间到达、等回合结束再处理的输入。 */
  private readonly running = new Set<string>()
  private readonly queuedInputs = new Map<string, string[]>()
  private readonly turnCounts = new Map<string, number>()
  /** stop/retry 后的迟到回合：不再写报告，避免落到已结束 assignment。 */
  private readonly cancelledAssignments = new Set<string>()

  constructor(options: SdkDshExecutorOptions) {
    this.options = options
    this.loadSessions()
  }

  async launch(assignment: Assignment, ticket: Ticket): Promise<void> {
    this.assignmentByTicket.set(ticket.id, assignment.id)
    const raw = this.options.describeTicket?.(ticket.id) ?? ''
    const spilled = spillInstruction(ticket, raw, {
      threshold: this.options.spillChars ?? 4000,
      dir: this.options.spillDir ?? join(process.cwd(), '.seed', 'spills'),
    })
    // 异步执行：launch 只负责"受理并启动"，回合结束后经 onReport 写回引擎。
    void this.runTurn(assignment.id, ticket, workerPrompt(ticket, spilled.inline, [], this.options.recallIndexPath, this.ticketDirectory(ticket)))
  }

  async deliver(ticket: Ticket, input: Input): Promise<void> {
    const assignmentId = this.assignmentByTicket.get(ticket.id) ?? ''
    // 全双工：回合进行中到达的新输入先排队，等当前回合结束立刻作为下一轮输入处理；
    // 绝不并发调用同一个 session（否则 DSH runtime 会排队/报错）。
    if (this.running.has(ticket.id)) {
      const pending = this.queuedInputs.get(ticket.id) ?? []
      pending.push(input.ref)
      this.queuedInputs.set(ticket.id, pending)
      return
    }
    void this.runTurn(assignmentId, ticket, input.ref)
  }

  /** 该工单还有多少条输入在排队（面板/验收可读）。 */
  pendingInputs(ticketId: string): number {
    return this.queuedInputs.get(ticketId)?.length ?? 0
  }

  /** 回合是否仍在进行（host 用它判断新消息该直投还是排队）。 */
  isRunning(ticketId: string): boolean {
    return this.running.has(ticketId)
  }

  /** 该工单已经跑过多少轮（全双工验收：第二轮确实被处理）。 */
  turnCount(ticketId: string): number {
    return this.turnCounts.get(ticketId) ?? 0
  }

  /**
   * 投机执行（文章 §3.4）：不进工单、不经过 Router，直接用独立 runtime 在后台尝试；
   * 结果交给调用方决定交付还是丢弃。
   */
  async runStandalone(prompt: string, dir: string): Promise<string> {
    mkdirSync(dir, { recursive: true })
    const harness = new DeepSeekHarness({ ...this.options.harness, cwd: dir })
    try {
      const result = await harness.run(prompt)
      return result.finalResponse.trim()
    } finally {
      await harness.close()
    }
  }

  /** 回合进行中直接把新输入排进 executor 队列，等当前回合结束立即处理。 */
  enqueueInput(ticketId: string, text: string): void {
    const pending = this.queuedInputs.get(ticketId) ?? []
    pending.push(text)
    this.queuedInputs.set(ticketId, pending)
  }

  async stop(assignment: Assignment): Promise<void> {
    this.cancelledAssignments.add(assignment.id)
    this.queuedInputs.delete(assignment.ticketId)
    this.running.delete(assignment.ticketId)
    const harness = this.harnessByTicket.get(assignment.ticketId)
    if (harness) {
      this.harnessByTicket.delete(assignment.ticketId)
      await harness.close().catch(() => undefined)
    }
  }

  /** 关闭所有 DSH runtime 子进程。 */
  async close(): Promise<void> {
    await Promise.all([...this.harnessByTicket.values()].map((harness) => harness.close()))
    this.harnessByTicket.clear()
  }

  /** 每个工单一个 runtime（cwd = 工单目录），实现工单级工作目录与上下文隔离。 */
  private client(ticket: Ticket): DshHarnessLike {
    const existing = this.harnessByTicket.get(ticket.id)
    if (existing) return existing
    const dir = this.options.ticketDir?.(ticket)
    if (dir) mkdirSync(dir, { recursive: true })
    const config: DeepSeekHarnessOptions = {
      ...this.options.harness,
      ...(dir ? { cwd: dir } : {}),
    }
    const harness = this.options.harnessFactory
      ? this.options.harnessFactory(config)
      : new DeepSeekHarness(config)
    this.harnessByTicket.set(ticket.id, harness)
    return harness
  }

  private ticketDirectory(ticket: Ticket): string | undefined {
    const dir = this.options.ticketDir?.(ticket)
    if (dir) mkdirSync(dir, { recursive: true })
    return dir
  }

  private async runTurn(assignmentId: string, ticket: Ticket, prompt: string): Promise<void> {
    if (this.cancelledAssignments.has(assignmentId)) return
    this.options.onPrompt?.(ticket.id, prompt)
    this.running.add(ticket.id)
    this.turnCounts.set(ticket.id, (this.turnCounts.get(ticket.id) ?? 0) + 1)
    const sessionId = this.sessionByTicket.get(ticket.id)
    const harness = this.client(ticket)
    try {
      let session: DshSessionLike
      if (sessionId) {
        try {
          session = await harness.resumeSession(sessionId)
        } catch {
          // 持久化的 session 在 runtime home 里已不存在：回退到新 session。
          this.sessionByTicket.delete(ticket.id)
          this.persistSessions()
          session = harness.session()
        }
      } else {
        session = harness.session()
      }
      const result = await session.run(prompt)
      if (this.cancelledAssignments.has(assignmentId)) return
      this.sessionByTicket.set(ticket.id, result.sessionId)
      this.persistSessions()
      this.options.onReport(reportOf(ticket, assignmentId, statusFor(result), summarize(result, this.options.maxSummaryChars), this.options.clock.now()))
    } catch (error) {
      if (this.cancelledAssignments.has(assignmentId)) return
      this.options.onReport(reportOf(ticket, assignmentId, 'failed', String(error).slice(0, 800), this.options.clock.now()))
    } finally {
      if (this.cancelledAssignments.has(assignmentId)) {
        this.running.delete(ticket.id)
        this.queuedInputs.delete(ticket.id)
        return
      }
      this.running.delete(ticket.id)
      const pending = this.queuedInputs.get(ticket.id)
      if (pending && pending.length > 0) {
        this.queuedInputs.delete(ticket.id)
        // 回合结束立即处理积压输入：前台在后台工作期间始终可接受新指令。
        void this.runTurn(assignmentId, ticket, pending.join('\n\n'))
      }
    }
  }

  private loadSessions(): void {
    const path = this.options.sessionStorePath
    if (!path || !existsSync(path)) return
    try {
      const payload = JSON.parse(readFileSync(path, 'utf8')) as { sessions?: unknown }
      if (!payload.sessions || typeof payload.sessions !== 'object') return
      for (const [ticketId, sessionId] of Object.entries(payload.sessions)) {
        if (typeof sessionId === 'string' && sessionId) this.sessionByTicket.set(ticketId, sessionId)
      }
    } catch {
      // 损坏的会话索引不应阻止 host 启动；下一次成功回合会重建。
    }
  }

  private persistSessions(): void {
    const path = this.options.sessionStorePath
    if (!path) return
    try {
      mkdirSync(dirname(path), { recursive: true })
      const temp = `${path}.tmp`
      writeFileSync(temp, JSON.stringify({ version: 1, sessions: Object.fromEntries(this.sessionByTicket) }), 'utf8')
      renameSync(temp, path)
    } catch {
      // 持久化失败只影响重启后的上下文复用，不影响当前回合。
    }
  }
}

function reportOf(ticket: Ticket, assignmentId: string, status: ReportStatus, summary: string, at: number): Report {
  return { ticketId: ticket.id, assignmentId, status, summary, at }
}

/** worker 提示词：只做一件事，结束时给结论。 */
export function workerPrompt(
  ticket: Ticket,
  instruction = '',
  inputs: readonly Trigger[] = [],
  recallIndexPath?: string,
  ticketDir?: string,
): string {
  const lines = [
    `你是 Super-agent 的 worker，工单 ${ticket.shortName}（${ticket.id}）。`,
    `授权范围：${ticket.mandate.scope}；强度：${ticket.mandate.strength}。`,
    '在当前工作目录内完成任务；不要与人对齐，不要请求确认。',
    '只做任务所需的最小操作；不要无目的地浏览仓库或重复尝试；完成后直接给出结论。',
  ]
  if (ticketDir) lines.splice(2, 0, `工作目录（产物写在这里）：${ticketDir}`)
  if (recallIndexPath) {
    lines.push(
      '',
      `上下文索引（需要追溯细节时用读取工具打开）：${recallIndexPath}`,
      '索引里有 triggers / threads / tickets；从一条事件出发，沿 threadIds / ticketIds 逐跳读取即可（链式召回）。',
    )
  }
  if (instruction.trim()) lines.push('', '任务：', instruction.trim())
  for (const input of inputs) lines.push(`- [${input.id}] ${input.actor}: ${input.text}`)
  return lines.join('\n')
}

function summarize(result: RunResult, maxChars = 20_000): string {
  const text = result.finalResponse.trim()
  if (!text) return `worker ended without final text (finishReason=${String(result.finishReason)})`
  return text.length > maxChars ? `${text.slice(0, maxChars)}…` : text
}

function statusFor(result: RunResult): ReportStatus {
  const reason = String(result.finishReason ?? '').toLowerCase()
  if (reason.includes('error') || reason.includes('abort') || reason.includes('max')) return 'failed'
  if (reason.includes('question') || reason.includes('input') || reason.includes('pause')) return 'blocked'
  return 'ready'
}