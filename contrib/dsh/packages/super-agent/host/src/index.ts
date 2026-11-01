/**
 * Super-agent host 插件：把事件溯源引擎挂到 DSH 的 cordis 生命周期上。
 *
 * 服务名：`superAgent`
 * 能力：ingest / state / tickets / ticket / tick / retry / reply / pause / resume
 *
 * 执行器：配置了 dshHome 时走 SdkDshExecutor（真实 DSH runtime 子进程 + 工具），
 * 否则用 PendingDshExecutor 占位（仅记录派工，用于无 DSH 环境的单测）。
 */

import { mkdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { Context, Service } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import type {} from '@deepseek-ai/dsh-host-webserver'
import {
  LlmAssessor,
  OpenAIClient,
  Runtime,
  SystemClock,
  Watchdog,
  buildPolicy,
  type AssessContext,
  type Assessor,
  type Decision,
  type Executor,
  type Assignment,
  type Input,
  type Policy,
  type Report,
  type Source,
  type State,
  type Ticket,
  type Trigger,
  type WatchdogReport,
} from '@deepseek-ai/dsh-super-agent-core'
import { SdkDshExecutor } from './executor.ts'
export { spillInstruction, workerPrompt } from './executor.ts'
import { RouterSession, createRouterClient, type RouterBatch } from './router_session.ts'
import { FeishuHttpClient } from './sources/feishu_http.ts'
import { FeishuSource } from './sources/feishu.ts'
import { GhCliClient } from './sources/github_cli.ts'
import { GitHubSource } from './sources/github.ts'
import { JsonlInboxSource } from './sources/jsonl.ts'
export { FeishuHttpClient } from './sources/feishu_http.ts'
export { FeishuSource, feishuThreadAddress } from './sources/feishu.ts'
export { GhCliClient } from './sources/github_cli.ts'
export { GitHubSource, threadAddress } from './sources/github.ts'
export { JsonlInboxSource } from './sources/jsonl.ts'
import { MultiChannelWriter } from './channels.ts'
import { mountHttpRoutes, type CommandInput } from './http.ts'

export interface SuperAgentHostConfig {
  /** 事件库路径；相对进程工作目录。 */
  dbPath: string
  /** 并发槽位。 */
  slots: number
  /** DSH runtime 的模块入口（省略则不用 SDK 执行器）。 */
  dshBin: string
  /** DSH home（SDK 要求隔离 home；空则不用 SDK 执行器）。 */
  dshHome: string
  dshProfile: string
  dshProvider: string
  dshModel: string
  /** 额外的 profile patch 文件（如 provider 配置）。 */
  dshPatch: string
  /** worker 工作目录（默认进程 cwd）。 */
  workspace: string
  /** 看门狗巡检间隔（秒）；0 关闭。 */
  watchdogSeconds: number
  /** 停滞判定阈值（秒）。 */
  staleSeconds: number
  /** 出站渠道开关（飞书/GitHub/本地日志）。 */
  channelsEnabled: boolean
  /** 嵌套 DSH runtime 的权限模式（headless 默认自动放行）。 */
  dshPermissionMode: string
  /** 评估器：explicit = Gate 放行即接受；llm = 模型按 assessment prompt 判定。 */
  assessorMode: string
  /** Router 形态：llm = 常驻 Router Session（跨 Thread 批处理 + 记忆 + 对话）；off = 单次评估器。 */
  routerMode: string
  /** Router 保留的对话消息数。 */
  routerHistoryMessages: number
  llmBaseUrl: string
  llmApiKeyEnv: string
  llmModel: string
  llmTimeoutMs: number
  /** Inline & Spill：指令超过该字符数就落盘，prompt 只留摘要 + 路径。 */
  spillChars: number
  /** 落盘目录（默认事件库同级的 spills/）。 */
  spillDir: string
  /** 入站 Source 总开关。 */
  sourcesEnabled: boolean
  /** 飞书群 chat_id 列表（逗号分隔；空 = 不启用飞书入站）。 */
  sourceFeishuChatIds: string
  /** 飞书只处理最近 N 秒的消息。 */
  sourceFeishuSinceSeconds: number
  /** GitHub 仓库列表（owner/name，逗号分隔；空 = 不启用 GitHub 入站）。 */
  sourceGithubRepos: string
  /** 只关心这些 reason（逗号分隔）。 */
  sourceGithubReasons: string
  /** JSONL 收件箱路径（本地联调）。 */
  sourceJsonlPath: string
  /** 轮询间隔（秒）。 */
  sourceIntervalSeconds: number
}

/** 显式准入：Gate 已放行则接受。M3 后续接 DSH LLM 评估。 */
const explicitAssessor: Assessor = {
  assess(_context: AssessContext): Decision {
    return { kind: 'accept', strength: 'explicit', reason: 'gate-passed', rules: [], scope: 'ticket' }
  },
}

/** 占位执行器：只记录派工，不执行（无 DSH 环境时用于单测）。 */
class PendingDshExecutor implements Executor {
  readonly launched: { assignmentId: string; ticketId: string }[] = []
  async launch(assignment: Assignment, ticket: Ticket): Promise<void> {
    this.launched.push({ assignmentId: assignment.id, ticketId: ticket.id })
  }
  async deliver(_ticket: Ticket, _input: Input): Promise<void> {}
  async stop(_assignment: Assignment): Promise<void> {}
}

export class SuperAgentHost extends Service {
  static inject: string[] = []

  static Config = z.object({
    dbPath: z.string().default('.seed/super-agent.db'),
    slots: z.number().step(1).min(1).max(16).default(2),
    dshBin: z.string().default(''),
    dshHome: z.string().default(''),
    dshProfile: z.string().default('sdk'),
    dshProvider: z.string().default('deepseek-official'),
    dshModel: z.string().default('deepseek-v4-flash'),
    dshPatch: z.string().default(''),
    workspace: z.string().default(''),
    watchdogSeconds: z.number().step(1).min(0).max(3600).default(60),
    staleSeconds: z.number().step(1).min(1).max(86400).default(1800),
    channelsEnabled: z.boolean().default(true),
    dshPermissionMode: z.string().default('danger-full-access'),
    assessorMode: z.string().default('llm'),
    routerMode: z.string().default('llm'),
    routerHistoryMessages: z.number().step(1).min(2).max(200).default(20),
    llmBaseUrl: z.string().default('https://token-plan.maas.qianwenaiapi.com/compatible-mode/v1'),
    llmApiKeyEnv: z.string().default('BAILIAN_API_KEY'),
    llmModel: z.string().default('deepseek-v4.1-flash'),
    llmTimeoutMs: z.number().step(1).min(1000).max(600000).default(60000),
    spillChars: z.number().step(1).min(200).max(1_000_000).default(4000),
    spillDir: z.string().default(''),
    sourcesEnabled: z.boolean().default(true),
    sourceFeishuChatIds: z.string().default(''),
    sourceFeishuSinceSeconds: z.number().step(1).min(30).max(86400).default(1800),
    sourceGithubRepos: z.string().default(''),
    sourceGithubReasons: z.string().default('mention,review_requested,comment,assign,team_mention'),
    sourceJsonlPath: z.string().default(''),
    sourceIntervalSeconds: z.number().step(1).min(1).max(3600).default(15),
  })

  readonly runtime: Runtime
  private readonly pending: PendingDshExecutor | undefined
  private readonly sdk: SdkDshExecutor | undefined
  private readonly dbPath: string
  private readonly watchdog: Watchdog
  private readonly channels: MultiChannelWriter
  private readonly channelsEnabled: boolean
  private readonly assessorMode: string
  private routerSession: RouterSession | undefined
  private lastRouterBatch: RouterBatch | undefined
  private readonly sourceList: Source[] = []
  private lastPollAt: number | undefined
  private readonly lastPrompts = new Map<string, string>()
  private lastWatchdog: WatchdogReport | undefined

  constructor(ctx: Context, config: SuperAgentHostConfig) {
    super(ctx, 'superAgent')
    this.dbPath = resolve(config.dbPath)
    mkdirSync(dirname(this.dbPath), { recursive: true })
    this.channelsEnabled = config.channelsEnabled
    this.assessorMode = config.assessorMode

    const clock = new SystemClock()
    const feishuAppId = process.env.FEISHU_APP_ID?.trim()
    const feishuAppSecret = process.env.FEISHU_APP_SECRET?.trim()
    this.channels = new MultiChannelWriter({
      ...(feishuAppId && feishuAppSecret ? { feishu: { appId: feishuAppId, appSecret: feishuAppSecret } } : {}),
      log: (line) => console.log(line),
    })
    let runtime: Runtime | undefined
    const onReport = (report: Report): void => {
      runtime?.engine.report(report)
      // 报告落地后立刻驱动一轮：Router 排队对外回复、派工继续。
      void this.tick().catch((error: unknown) => {
        console.error('super-agent: tick after report failed', String(error))
      })
    }

    if (config.dshBin && config.dshHome) {
      this.sdk = new SdkDshExecutor({
        clock,
        onPrompt: (ticketId, prompt) => {
          this.lastPrompts.set(ticketId, prompt)
          if (this.lastPrompts.size > 50) {
            const oldest = this.lastPrompts.keys().next().value
            if (oldest) this.lastPrompts.delete(oldest)
          }
        },
        spillChars: config.spillChars,
        spillDir: config.spillDir ? resolve(config.spillDir) : join(dirname(this.dbPath), 'spills'),
        describeTicket: (ticketId) => {
          const state = this.runtime?.engine.state
          const ticket = state?.tickets[ticketId]
          if (!state || !ticket) return ''
          const direct = state.triggers[ticket.mandate.triggerId]
          if (direct?.text) return direct.text
          // 兜底：同线程里最近的一条 trigger（mandate 指向的 id 可能已被替代）。
          const related = Object.values(state.triggers)
            .filter((trigger) => trigger.threadIds.some((threadId) => ticket.threadIds.includes(threadId)))
            .sort((a, b) => b.at - a.at)
          return related[0]?.text ?? ''
        },
        harness: {
          dshBin: config.dshBin,
          dshHome: config.dshHome,
          profile: config.dshProfile,
          provider: config.dshProvider,
          model: config.dshModel,
          // 在 Electron 宿主里 process.execPath 是 electron.exe：必须让子进程以 node 模式跑，
          // 否则 spawn 出来的是一个新 Electron 应用，SDK 握手永远不完成。
          env: {
            ...process.env,
            ...(process.versions.electron ? { ELECTRON_RUN_AS_NODE: '1' } : {}),
            // headless worker：工具调用自动放行（DSH_PERMISSION_MODE 同时决定 sandbox 与 approval）。
            DSH_PERMISSION_MODE: config.dshPermissionMode,
          },
          ...(config.dshPatch ? { patches: [resolve(config.dshPatch)] } : {}),
          ...(config.workspace ? { cwd: resolve(config.workspace) } : {}),
        },
        onReport,
      })
      this.pending = undefined
    } else {
      this.pending = new PendingDshExecutor()
      this.sdk = undefined
    }

    runtime = Runtime.build({
      assessor: this.buildAssessor(config),
      executor: this.sdk ?? this.pending!,
      clock,
      config: {
        dbPath: this.dbPath,
        slots: config.slots,
        policy: this.buildPolicy(config),
        ...(config.channelsEnabled ? { channels: this.channels } : {}),
      },
    })
    this.runtime = runtime
    this.watchdog = new Watchdog({ clock, staleSeconds: config.staleSeconds })
    ctx.effect(() => async () => {
      await this.sdk?.close()
      this.runtime.close()
    })

    // 入站 Source：轮询群消息/通知/JSONL，产生 Trigger（主动性的入口）。
    if (config.sourcesEnabled) {
      this.sourceList.push(...this.createSources(config))
      if (this.sourceList.length > 0) {
        const timer = setInterval(() => {
          void this.pollSources()
        }, config.sourceIntervalSeconds * 1000)
        timer.unref()
        ctx.effect(() => () => clearInterval(timer))
        void this.pollSources()
      }
    }

    // 外部看门狗：独立巡检（停滞/未投递），不依赖被测系统自证。
    if (config.watchdogSeconds > 0) {
      const timer = setInterval(() => {
        void this.agitate()
      }, config.watchdogSeconds * 1000)
      timer.unref()
      ctx.effect(() => () => clearInterval(timer))
    }

    // client 工作台：webServer 存在时挂 /super-agent/{state,command}。
    ctx.inject(['webServer'], (httpCtx) => {
      const routes = mountHttpRoutes({
        statePath: '/super-agent/state',
        commandPath: '/super-agent/command',
        snapshot: () => this.snapshot(),
        command: (input) => this.command(input),
      })
      const offState = httpCtx.webServer.register({ kind: 'exact', path: '/super-agent/state', handler: routes.state })
      const offCommand = httpCtx.webServer.register({ kind: 'exact', path: '/super-agent/command', handler: routes.command })
      httpCtx.effect(() => () => {
        offState()
        offCommand()
      })
    })
  }

  get storePath(): string {
    return this.dbPath
  }

  /** true 表示使用真实 DSH runtime 执行；false 表示占位执行器。 */
  get usesDshRuntime(): boolean {
    return this.sdk !== undefined
  }

  /** 占位执行器的派工记录（仅占位模式有意义）。 */
  get launched(): readonly { assignmentId: string; ticketId: string }[] {
    return this.pending?.launched ?? []
  }

  state(): State {
    return this.runtime.engine.state
  }

  tickets(): Ticket[] {
    return Object.values(this.runtime.engine.state.tickets).sort((a, b) => a.id.localeCompare(b.id))
  }

  ticket(id: string): Ticket | undefined {
    return this.runtime.engine.state.tickets[id]
  }

  ingest(trigger: Trigger): number {
    return this.runtime.engine.ingest(trigger).length
  }

  async tick(): Promise<boolean> {
    const before = this.runtime.store.lastSeq()
    await this.runtime.tickUntilIdle()
    return this.runtime.store.lastSeq() > before
  }

  retry(ticketId: string): void {
    this.runtime.engine.retry(ticketId)
  }

  reply(ticketId: string, text: string): void {
    this.runtime.engine.personMessage(ticketId, text)
  }

  pause(): void {
    this.runtime.engine.pause()
  }

  resume(): void {
    this.runtime.engine.resume()
  }

  get paused(): boolean {
    return this.runtime.engine.isPaused
  }

  replayHash(): string {
    return this.runtime.store.replayHash()
  }

  /** 按配置创建入站 Source（JSONL / 飞书 / GitHub）。 */
  private createSources(config: SuperAgentHostConfig): Source[] {
    const sources: Source[] = []
    if (config.sourceJsonlPath) sources.push(new JsonlInboxSource(resolve(config.sourceJsonlPath)))

    const feishuChats = config.sourceFeishuChatIds.split(',').map((value) => value.trim()).filter(Boolean)
    const feishuAppId = process.env.FEISHU_APP_ID?.trim()
    const feishuAppSecret = process.env.FEISHU_APP_SECRET?.trim()
    if (feishuChats.length > 0 && feishuAppId && feishuAppSecret) {
      sources.push(new FeishuSource(
        new FeishuHttpClient({ appId: feishuAppId, appSecret: feishuAppSecret, chatIds: feishuChats }),
        { sinceSeconds: config.sourceFeishuSinceSeconds },
      ))
    }

    const repos = config.sourceGithubRepos.split(',').map((value) => value.trim()).filter(Boolean)
    if (repos.length > 0) {
      const reasons = config.sourceGithubReasons.split(',').map((value) => value.trim()).filter(Boolean)
      sources.push(new GitHubSource({
        client: new GhCliClient({
          excludeSelf: true,
          ...(config.workspace ? { cwd: resolve(config.workspace) } : {}),
        }),
        clock: new SystemClock(),
        repos,
        reasons,
      }))
    }
    return sources
  }

  /** 准入策略：本地恒允许；配置了入站的 source 也允许（更细的来源/群组规则在下一轮补）。 */
  private buildPolicy(config: SuperAgentHostConfig): Policy {
    const rules = [{ source: 'local', actor: '*', allow: true, strength: 'explicit' as const, note: 'local-explicit' }]
    const senders: [string, string][] = [['local', '*']]
    if (config.sourceFeishuChatIds.trim()) {
      rules.push({ source: 'feishu', actor: '*', allow: true, strength: 'explicit' as const, note: 'feishu-inbound' })
      senders.push(['feishu', '*'])
    }
    if (config.sourceGithubRepos.trim()) {
      rules.push({ source: 'github', actor: '*', allow: true, strength: 'explicit' as const, note: 'github-inbound' })
      senders.push(['github', '*'])
    }
    return buildPolicy(rules, 'auto', senders)
  }

  /** 轮询所有入站 Source：新 Trigger 进引擎并驱动一轮（幂等由 engine 的 trigger id 保证）。 */
  async pollSources(): Promise<void> {
    if (this.runtime.engine.isPaused) return
    for (const source of this.sourceList) {
      try {
        const triggers = await source.poll()
        let ingested = 0
        for (const trigger of triggers) ingested += this.ingest(trigger)
        if (ingested > 0) await this.tick()
      } catch (error) {
        console.error(`super-agent source ${source.name} poll failed`, String(error))
      }
    }
    this.lastPollAt = Math.floor(Date.now() / 1000)
  }

  /** 逐轮评估：explicit（Gate 放行即接受）或 llm（真实模型两级过滤；routerMode=llm 时走常驻 Router Session）。 */
  private buildAssessor(config: SuperAgentHostConfig): Assessor {
    if (config.assessorMode !== 'llm') return explicitAssessor
    const apiKey = process.env[config.llmApiKeyEnv]?.trim()
    if (!apiKey) {
      console.warn(`super-agent: ${config.llmApiKeyEnv} missing, falling back to explicit assessor`)
      return explicitAssessor
    }
    if (config.routerMode === 'llm') {
      const router = new RouterSession({
        client: createRouterClient({
          baseUrl: config.llmBaseUrl,
          apiKey,
          model: config.llmModel,
          timeoutMs: config.llmTimeoutMs,
        }),
        // runtime 在构造函数后半段才赋值；这里只登记读取方式，首次 assess 时 runtime 已就绪。
        state: () => this.runtime.engine.state,
        historyMessages: config.routerHistoryMessages,
        onBatch: (batch) => {
          this.lastRouterBatch = batch
        },
      })
      this.routerSession = router
      return router
    }
    return new LlmAssessor(new OpenAIClient({
      baseUrl: config.llmBaseUrl,
      apiKey,
      model: config.llmModel,
      timeoutMs: config.llmTimeoutMs,
      temperature: 0,
      maxTokens: 800,
    }))
  }

  /** 跑一次看门狗巡检；intervene 时对每个 finder 触达的工单 retry 并驱动一轮。 */
  async checkWatchdog(): Promise<WatchdogReport> {
    const report = await this.watchdog.check(this.runtime.engine.state)
    this.lastWatchdog = report
    if (report.verdict.action === 'intervene') {
      for (const finding of report.findings) {
        try {
          this.runtime.engine.retry(finding.ticketId)
        } catch (error) {
          // 不可重试的工单（已结束/无派工）不影响其它 finding。
          console.error('super-agent watchdog: retry skipped', finding.ticketId, String(error))
        }
      }
      void this.tick()
    }
    return report
  }

  private async agitate(): Promise<void> {
    try {
      await this.checkWatchdog()
    } catch (error) {
      console.error('super-agent watchdog: check failed', String(error))
    }
  }

  /** 给 client 工作台的状态快照（读模型，不含副作用）。 */
  snapshot(): unknown {
    const state = this.runtime.engine.state
    const tickets = this.tickets().map((ticket) => {
      const reports = state.reports[ticket.id] ?? []
      const assignment = Object.values(state.assignments).find((a) => a.ticketId === ticket.id)
      const origin = state.triggers[ticket.mandate.triggerId]
      return {
        id: ticket.id,
        shortName: ticket.shortName,
        state: ticket.state,
        title: origin?.text?.slice(0, 160) ?? '',
        source: origin?.source ?? '',
        actor: origin?.actor ?? '',
        assignment: assignment ? { id: assignment.id, state: assignment.state } : null,
        channelIds: ticket.channelIds,
        lastPrompt: (this.lastPrompts.get(ticket.id) ?? '').slice(0, 400),
        reports: reports.slice(-3).map((report) => ({
          status: report.status,
          summary: report.summary,
          at: report.at,
        })),
        updatedAt: (reports.at(-1)?.at ?? origin?.at ?? 0),
      }
    })
    return {
      ok: true,
      paused: this.paused,
      usesDshRuntime: this.usesDshRuntime,
      storePath: this.storePath,
      replayHash: this.replayHash(),
      lastSeq: this.runtime.store.lastSeq(),
      watchdog: this.lastWatchdog
        ? { findings: this.lastWatchdog.findings.length, action: this.lastWatchdog.verdict.action }
        : null,
      channels: {
        enabled: this.channelsEnabled,
        feishu: Boolean(process.env.FEISHU_APP_ID && process.env.FEISHU_APP_SECRET),
        sent: this.channels.history.slice(-5),
      },
      assessorMode: this.assessorMode,
      router: this.routerSession
        ? { mode: 'llm', ...this.routerSession.snapshot() }
        : { mode: this.assessorMode, lastBatch: this.lastRouterBatch ?? null },
      sources: {
        enabled: this.sourceList.length > 0,
        names: this.sourceList.map((source) => source.name),
        lastPollAt: this.lastPollAt ?? null,
      },
      tickets: tickets.sort((a, b) => b.updatedAt - a.updatedAt),
    }
  }

  /** client 发来的命令（人的干预 + 与 Router 对话）。 */
  async command(input: CommandInput): Promise<unknown> {
    const ticketId = input.ticketId ?? ''
    let reply: string | undefined
    switch (input.action) {
      case 'pause':
        this.pause()
        break
      case 'resume':
        this.resume()
        break
      case 'retry':
        if (!ticketId) throw new Error('ticketId required')
        this.retry(ticketId)
        break
      case 'reply':
        if (!ticketId || !input.text) throw new Error('ticketId and text required')
        this.reply(ticketId, input.text)
        break
      case 'ingest': {
        if (!input.text) throw new Error('text required')
        const now = Math.floor(Date.now() / 1000)
        const address = input.channel?.trim() || 'local:super-agent'
        this.ingest({
          id: `trg-local-${now}-${Math.random().toString(36).slice(2, 8)}`,
          source: 'local',
          actor: 'human',
          text: input.text,
          threadIds: [address],
          channelIds: [address],
          at: now,
        })
        void this.tick()
        break
      }
      case 'chat': {
        if (!input.text) throw new Error('text required')
        if (!this.routerSession) throw new Error('router session not enabled (routerMode=off)')
        reply = await this.routerSession.chat(input.text)
        break
      }
      default:
        throw new Error(`unknown action: ${String(input.action)}`)
    }
    const snapshot = this.snapshot() as Record<string, unknown>
    return reply === undefined ? snapshot : { ...snapshot, reply }
  }
}

export default SuperAgentHost