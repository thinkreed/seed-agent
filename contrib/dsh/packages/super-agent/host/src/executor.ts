/**
 * DSH SDK 执行器：把一个 Assignment 变成一个真实的 DSH session 回合。
 *
 * 走官方 @deepseek-ai/dsh-sdk-client：`DeepSeekHarness.run(prompt)` 会拉起一个
 * DSH runtime 子进程（真实模型 + 工具 + 沙箱），返回该回合的最终文本。
 * 每次执行对应一个 session；同一工单的后续投递复用该 sessionId。
 *
 * 这是「存算分离」的计算侧：状态仍在 Super-agent 事件库，执行在 DSH runtime。
 */

import type { DeepSeekHarnessOptions, RunResult } from '@deepseek-ai/dsh-sdk-client'
import { DeepSeekHarness } from '@deepseek-ai/dsh-sdk-client'
import type { Assignment, Clock, Executor, Input, Report, ReportStatus, Ticket, Trigger } from '@deepseek-ai/dsh-super-agent-core'

export interface SdkDshExecutorOptions {
  /** 传给 SDK 的启动配置（dshBin / dshHome / profile / provider / model…）。 */
  readonly harness: DeepSeekHarnessOptions
  /** worker 的工作目录。 */
  readonly workspace?: string
  readonly clock: Clock
  /** 把结果写回引擎（engine.report）。 */
  readonly onReport: (report: Report) => void
  /** 取工单的原始指令文本（source trigger / inputs）。 */
  readonly describeTicket?: (ticketId: string) => string
  /** 观察每次真正发给 DSH worker 的提示词（验收/调试）。 */
  readonly onPrompt?: (ticketId: string, prompt: string) => void
}

export class SdkDshExecutor implements Executor {
  private harness: DeepSeekHarness | undefined
  private readonly options: SdkDshExecutorOptions
  private readonly sessionByTicket = new Map<string, string>()
  private readonly assignmentByTicket = new Map<string, string>()

  constructor(options: SdkDshExecutorOptions) {
    this.options = options
  }

  async launch(assignment: Assignment, ticket: Ticket): Promise<void> {
    this.assignmentByTicket.set(ticket.id, assignment.id)
    // 异步执行：launch 只负责"受理并启动"，回合结束后经 onReport 写回引擎。
    void this.runTurn(assignment.id, ticket, workerPrompt(ticket, this.options.describeTicket?.(ticket.id) ?? ''))
  }

  async deliver(ticket: Ticket, input: Input): Promise<void> {
    const assignmentId = this.assignmentByTicket.get(ticket.id) ?? ''
    void this.runTurn(assignmentId, ticket, input.ref)
  }

  async stop(_assignment: Assignment): Promise<void> {
    // M3.1：SDK 目前没有按回合取消的公开 API；依赖 turn 自己结束或 ctx 关闭时关进程。
  }

  /** 关闭 DSH runtime 子进程。 */
  async close(): Promise<void> {
    await this.harness?.close()
    this.harness = undefined
  }

  private client(): DeepSeekHarness {
    this.harness ??= new DeepSeekHarness(this.options.harness)
    return this.harness
  }

  private async runTurn(assignmentId: string, ticket: Ticket, prompt: string): Promise<void> {
    this.options.onPrompt?.(ticket.id, prompt)
    const sessionId = this.sessionByTicket.get(ticket.id)
    try {
      const result = await this.client().run(prompt, sessionId ? { sessionId } : {})
      this.sessionByTicket.set(ticket.id, result.sessionId)
      this.options.onReport(reportOf(ticket, assignmentId, 'ready', summarize(result), this.options.clock.now()))
    } catch (error) {
      this.options.onReport(reportOf(ticket, assignmentId, 'failed', String(error).slice(0, 400), this.options.clock.now()))
    }
  }
}

function reportOf(ticket: Ticket, assignmentId: string, status: ReportStatus, summary: string, at: number): Report {
  return { ticketId: ticket.id, assignmentId, status, summary, at }
}

/** worker 提示词：只做一件事，结束时给结论。 */
export function workerPrompt(ticket: Ticket, instruction = '', inputs: readonly Trigger[] = []): string {
  const lines = [
    `你是 Super-agent 的 worker，工单 ${ticket.shortName}（${ticket.id}）。`,
    `授权范围：${ticket.mandate.scope}；强度：${ticket.mandate.strength}。`,
    '在当前工作目录内完成任务；不要与人对齐，不要请求确认。',
    '完成后用一段话给出结论（做了什么、产物在哪里、是否成功）。',
  ]
  if (instruction.trim()) lines.push('', '任务：', instruction.trim())
  for (const input of inputs) lines.push(`- [${input.id}] ${input.actor}: ${input.text}`)
  return lines.join('\n')
}

function summarize(result: RunResult): string {
  const text = result.finalResponse.trim()
  const bounded = text.length > 600 ? `${text.slice(0, 600)}…` : text
  return bounded || `done (finishReason=${String(result.finishReason)})`
}