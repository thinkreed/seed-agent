/**
 * 独立 Watchdog session 裁定（文章 §6）：
 * 巡检发现交给一个主系统之外的 DSH 会话（独立工作目录、独立回合），由模型判断是否真的需要介入。
 * 与 LlmWatchdogJudge 的区别：不走 host 的内联模型调用，而是真实拉起 DSH runtime 会话。
 */
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import type { State, WatchdogFinding, WatchdogJudge, WatchdogVerdict } from '@deepseek-ai/dsh-super-agent-core'
import { extractJsonObject } from '@deepseek-ai/dsh-super-agent-core'

/** 最小可用的独立会话执行器（SdkDshExecutor.runStandalone 满足该形状）。 */
export interface StandaloneSessionRunner {
  runStandalone(prompt: string, dir: string): Promise<string>
}

/** 把 findings 交给独立 DSH session，要求只回 JSON。 */
export class DshWatchdogJudge implements WatchdogJudge {
  private readonly runner: StandaloneSessionRunner
  private readonly workspace: string
  private readonly maxFindings: number

  constructor(runner: StandaloneSessionRunner, workspace: string, maxFindings = 20) {
    this.runner = runner
    this.workspace = workspace
    this.maxFindings = maxFindings
  }

  async judge(findings: readonly WatchdogFinding[], state: State): Promise<WatchdogVerdict> {
    const dir = join(this.workspace, '.seed', 'watchdog')
    mkdirSync(dir, { recursive: true })
    const sample = findings.slice(0, this.maxFindings)
    const context = {
      findings: sample,
      openTickets: Object.values(state.tickets)
        .filter((ticket) => ticket.state === 'open')
        .map((ticket) => ({ id: ticket.id, shortName: ticket.shortName })),
    }
    const prompt = [
      '你是主系统之外的独立 Watchdog 会话，只负责判断巡检发现的事故是否需要人工/系统介入。',
      '判断标准：如果 Agent 确实在推进（只是慢），返回 ok；如果长时间停滞、报告未投递或有工单卡死，返回 intervene。',
      '只输出一个 JSON 对象，形如 {"action":"ok","reason":"一句话理由"} 或 {"action":"intervene","reason":"一句话理由"}。',
      '',
      '巡检输入：',
      JSON.stringify(context),
    ].join('\n')
    const raw = await this.runner.runStandalone(prompt, dir)
    const parsed = extractJsonObject(raw)
    const action = parsed?.action === 'intervene' ? 'intervene' : 'ok'
    const reason = typeof parsed?.reason === 'string' ? parsed.reason.slice(0, 300) : 'watchdog-session-judged'
    return { action, reason }
  }
}