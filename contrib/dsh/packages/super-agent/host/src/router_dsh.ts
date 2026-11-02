/**
 * 用 DSH Session 承载 Router 的模型调用。
 *
 * 目的：让 Router 与 Worker 一样复用同一套 DSH session/前缀缓存，而不是每次
 * 直接 new 一个 OpenAI 请求。Router 仍然只输出 JSON 协议结果，不使用工具。
 */

import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { dirname } from 'node:path'
import type { DeepSeekHarnessOptions, RunResult } from '@deepseek-ai/dsh-sdk-client'
import { DeepSeekHarness } from '@deepseek-ai/dsh-sdk-client'
import type { ModelClient, ModelMessage } from '@deepseek-ai/dsh-super-agent-core'

interface SessionHandle {
  run(prompt: string): Promise<RunResult>
}

interface HarnessLike {
  session(sessionId?: string): SessionHandle
  resumeSession(sessionId: string): Promise<SessionHandle>
  close(): Promise<void>
}

export interface DshRouterClientOptions {
  readonly harness: DeepSeekHarnessOptions
  readonly sessionStorePath?: string
  readonly harnessFactory?: (options: DeepSeekHarnessOptions) => HarnessLike
}

export class DshRouterClient implements ModelClient {
  private readonly options: DshRouterClientOptions
  private harness: HarnessLike | undefined
  private sessionId: string | undefined
  private started = false
  private queue: Promise<void> = Promise.resolve()

  constructor(options: DshRouterClientOptions) {
    this.options = options
    this.sessionId = this.loadSessionId()
  }

  complete(messages: readonly ModelMessage[]): Promise<string> {
    const task = this.queue.then(() => this.doComplete(messages))
    this.queue = task.then(
      () => undefined,
      () => undefined,
    )
    return task
  }

  async close(): Promise<void> {
    const harness = this.harness
    this.harness = undefined
    this.started = false
    if (harness) await harness.close().catch(() => undefined)
  }

  private async doComplete(messages: readonly ModelMessage[]): Promise<string> {
    const harness = await this.ensureHarness()
    const system = messages
      .filter((message) => message.role === 'system')
      .map((message) => message.content)
      .join('\n\n')
    const user = [...messages].reverse().find((message) => message.role === 'user')?.content ?? ''
    const transcript = messages.map((message) => `[${message.role}]\n${message.content}`).join('\n\n')
    // 已恢复的 session 只需要新输入；全新 session 需要完整协议上下文。
    const prompt = this.started
      ? `${user}\n\n只输出请求的 JSON，不要使用工具，不要解释。`
      : `[ROUTER PROTOCOL]\n${system}\n\n[CONVERSATION]\n${transcript}\n\n只输出请求的 JSON，不要使用工具，不要解释。`
    const result = await harness.session(this.sessionId).run(prompt)
    this.sessionId = result.sessionId
    this.started = true
    this.persistSessionId()
    return result.finalResponse.trim()
  }

  private async ensureHarness(): Promise<HarnessLike> {
    if (this.harness) return this.harness
    const harness = this.options.harnessFactory
      ? this.options.harnessFactory(this.options.harness)
      : new DeepSeekHarness({ ...this.options.harness, maxTokens: this.options.harness.maxTokens ?? 4096 })
    this.harness = harness
    if (this.sessionId) {
      try {
        await harness.resumeSession(this.sessionId)
        this.started = true
      } catch {
        this.sessionId = undefined
        this.persistSessionId()
        this.started = false
      }
    }
    return harness
  }

  private loadSessionId(): string | undefined {
    const path = this.options.sessionStorePath
    if (!path || !existsSync(path)) return undefined
    try {
      const parsed = JSON.parse(readFileSync(path, 'utf8')) as { sessionId?: unknown }
      return typeof parsed.sessionId === 'string' && parsed.sessionId ? parsed.sessionId : undefined
    } catch {
      return undefined
    }
  }

  private persistSessionId(): void {
    const path = this.options.sessionStorePath
    if (!path) return
    try {
      mkdirSync(dirname(path), { recursive: true })
      const temp = `${path}.tmp`
      writeFileSync(temp, JSON.stringify({ sessionId: this.sessionId ?? '' }), 'utf8')
      renameSync(temp, path)
    } catch {
      // Router 会话缓存失败不影响本轮；下次会新建 session。
    }
  }
}