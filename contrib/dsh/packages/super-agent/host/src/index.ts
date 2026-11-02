/**
 * Super-agent host 插件：把事件溯源引擎挂到 DSH 的 cordis 生命周期上。
 *
 * 服务名：`superAgent`
 * 能力：ingest / state / tickets / ticket / tick / retry / reply / pause / resume
 *
 * 执行器：配置了 dshHome 时走 SdkDshExecutor（真实 DSH runtime 子进程 + 工具），
 * 否则用 PendingDshExecutor 占位（仅记录派工，用于无 DSH 环境的单测）。
 */

import { existsSync, mkdirSync, readFileSync, readdirSync, unlinkSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
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
  recall,
  stageOf,
  type AssessContext,
  type RecallKind,
  type RecallResult,
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
export { RouterSession, createRouterClient } from './router_session.ts'
import { LlmWatchdogAdvisor, LlmWatchdogJudge, Speculator } from '@deepseek-ai/dsh-super-agent-core'
import { DshWatchdogAdvisor, DshWatchdogJudge } from './watchdog_session.ts'
import { recordSourceFailure, recordSourceRecovery } from '@deepseek-ai/dsh-super-agent-core'
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
export { MultiChannelWriter } from './channels.ts'
export { formatForChannel, compactForIm, structureForAsync, ChannelFormattingWriter } from './format.ts'
import { ChannelFormattingWriter } from './format.ts'
import { mountHttpRoutes, type CommandInput } from './http.ts'

/** 若路径被 Electron asar 打包，优先返回解包后的真实文件（普通 node 子进程读不了 asar）。 */
function unpackedPath(candidate: string): string {
  if (existsSync(candidate)) return candidate
  const unpacked = candidate.replace(`${sep}app.asar${sep}`, `${sep}app.asar.unpacked${sep}`)
  return unpacked !== candidate && existsSync(unpacked) ? unpacked : candidate
}

/** host 包根（lib 的上一级）。 */
function hostPackageRoot(): string {
  return resolve(dirname(fileURLToPath(import.meta.url)), '..')
}

/** 从 host 包位置推断 dsh 根（lib -> host -> super-agent -> packages -> dsh）。 */
function inferredDshRoot(): string {
  return resolve(dirname(fileURLToPath(import.meta.url)), '../../../..')
}

/** 捆绑模式下的运行路径推断；仅在字段为空时填充。 */
function resolveBundleDefaults(config: SuperAgentHostConfig): Partial<SuperAgentHostConfig> {
  const dshHome = config.dshHome || process.env.DSH_HOME?.trim() || join(homedir(), '.dsh')
  const resourcesPath = (process as NodeJS.Process & { resourcesPath?: string }).resourcesPath
  const resources = resourcesPath ? join(resourcesPath, 'dsh') : ''
  const externalBin = resources ? join(resources, 'node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js') : ''
  const dshBin = config.dshBin || (externalBin && existsSync(externalBin) ? externalBin : unpackedPath(join(inferredDshRoot(), 'node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js')))
  const dshPatch = config.dshPatch || unpackedPath(join(hostPackageRoot(), 'config', 'sdk-super-agent.patch.yml'))
  const workspace = config.workspace || join(dshHome, 'super-agent-workspace')
  return { dshHome, dshBin, dshPatch, workspace }
}

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
  /** 捆绑模式：未显式配置时，从 host 包位置推断 dshBin/dshHome/dshPatch/workspace（桌面安装包用）。 */
  bundleDefaults: boolean
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
  /** 飞书允许的发送者（逗号分隔；* = 全部）。 */
  sourceFeishuAllowedSenders: string
  /** GitHub 允许的 actor（逗号分隔；* = 全部）。 */
  sourceGithubAllowedActors: string
  /** 必须显式 @ 才准入的 Source（逗号分隔，如 feishu）。 */
  sourceMentionRequired: string
  /** 识别"显式请求"的提及词（逗号分隔）。 */
  mentionTokens: string
  /** JSONL 收件箱路径（本地联调）。 */
  sourceJsonlPath: string
  /** 轮询间隔（秒）。 */
  sourceIntervalSeconds: number
  /** 链式召回索引文件（默认事件库同级 recall-index.json；worker 通过它逐跳读上下文）。 */
  recallIndexPath: string
  /** Worker 控制请求目录（handback/unsubscribe 的文件式入口）。 */
  controlDir: string
  /** 额外召回索引（只读，供 fixture/归档与主索引合并查询）。 */
  recallExtraPath: string
  /** 每工单独立工作目录的根（默认 <workspace>/tickets）。 */
  ticketsDir: string
  /** 启动时恢复上次未收口的 assignment（文章 §5/执行语义）。 */
  recoverOnStart: boolean
  /** Watchdog 裁定：llm = 内联模型裁定；session = 独立 DSH session 裁定（文章 §6）；deterministic = 只看 findings。 */
  watchdogMode: string
  /** 投机执行开关（文章 §3.4）：后台尝试，有价值才交付。 */
  speculationEnabled: boolean
  /** 自动投机的 Source（逗号分隔，如 feishu）；空 = 只在手动命令时投机。 */
  speculationSources: string
  /** 端侧 daemon（存算分离，文章 §5.2）地址与令牌；worker 工具据此在真实环境执行。 */
  daemonUrl: string
  daemonToken: string
  /** 多设备端点 JSON：{"laptop":{"url":"...","token":"..."},...}，为空则只用 daemonUrl。 */
  daemonEndpointsJson: string
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
    bundleDefaults: z.boolean().default(false),
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
    sourceFeishuAllowedSenders: z.string().default('*'),
    sourceGithubAllowedActors: z.string().default('*'),
    sourceMentionRequired: z.string().default(''),
    mentionTokens: z.string().default('@seed,@agent'),
    sourceJsonlPath: z.string().default(''),
    sourceIntervalSeconds: z.number().step(1).min(1).max(3600).default(15),
    recallIndexPath: z.string().default(''),
    controlDir: z.string().default(''),
    recallExtraPath: z.string().default(''),
    ticketsDir: z.string().default(''),
    recoverOnStart: z.boolean().default(true),
    watchdogMode: z.string().default('llm'),
    speculationEnabled: z.boolean().default(true),
    speculationSources: z.string().default(''),
    daemonUrl: z.string().default(''),
    daemonToken: z.string().default(''),
    daemonEndpointsJson: z.string().default(''),
  })

  readonly runtime: Runtime
  private readonly pending: PendingDshExecutor | undefined
  private readonly sdk: SdkDshExecutor | undefined
  private readonly dbPath: string
  private readonly watchdog: Watchdog
  private readonly channels: MultiChannelWriter
  private readonly channelWriter: ChannelFormattingWriter
  private readonly channelsEnabled: boolean
  private readonly speculationEnabled: boolean
  private readonly speculator: Speculator | undefined
  private readonly watchdogMode: string
  private readonly assessorMode: string
  private routerSession: RouterSession | undefined
  private lastRouterBatch: RouterBatch | undefined
  private readonly sourceList: Source[] = []
  private readonly failedSources = new Set<string>()
  private readonly recallIndexPath: string
  private readonly controlDir: string
  private readonly recallExtraPath: string
  private readonly ticketsRoot: string
  private lastRecovery = 0
  private readonly interventions: { at: number; action: string; reason: string; findings: number }[] = []
  private rechecks = 0
  private lastPollAt: number | undefined
  private readonly lastPrompts = new Map<string, string>()
  private lastWatchdog: WatchdogReport | undefined
  private lastWatchdogAnswer: { at: number; question: string; answer: string } | undefined

  constructor(ctx: Context, config: SuperAgentHostConfig) {
    super(ctx, 'superAgent')
    // 桌面安装包（bundle 挂载）没有显式路径配置：从包位置推断。
    if (config.bundleDefaults) config = { ...config, ...resolveBundleDefaults(config) }
    this.dbPath = resolve(config.dbPath)
    mkdirSync(dirname(this.dbPath), { recursive: true })
    this.channelsEnabled = config.channelsEnabled
    this.speculationEnabled = config.speculationEnabled
    this.watchdogMode = config.watchdogMode
    this.assessorMode = config.assessorMode
    this.recallIndexPath = config.recallIndexPath
      ? resolve(config.recallIndexPath)
      : join(dirname(this.dbPath), 'recall-index.json')
    this.controlDir = config.controlDir
      ? resolve(config.controlDir)
      : join(dirname(this.dbPath), 'control')
    this.recallExtraPath = config.recallExtraPath ? resolve(config.recallExtraPath) : ''
    this.ticketsRoot = config.ticketsDir
      ? resolve(config.ticketsDir)
      : join(resolve(config.workspace || process.cwd()), 'tickets')

    const clock = new SystemClock()
    const feishuAppId = process.env.FEISHU_APP_ID?.trim()
    const feishuAppSecret = process.env.FEISHU_APP_SECRET?.trim()
    this.channels = new MultiChannelWriter({
      ...(feishuAppId && feishuAppSecret ? { feishu: { appId: feishuAppId, appSecret: feishuAppSecret } } : {}),
      outboxDir: join(resolve(config.workspace || process.cwd()), '.seed', 'outbox'),
      log: (line) => console.log(line),
    })
    this.channelWriter = new ChannelFormattingWriter(this.channels)
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
        recallIndexPath: this.recallIndexPath,
        ticketDir: (ticket) => join(this.ticketsRoot, ticket.id),
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
          // 冷启动/首次 profile 握手偶尔会超过 SDK 默认 10s（尤其是并行投机）。
          initializeTimeoutMs: 30_000,
          // 在 Electron 宿主里 process.execPath 是 electron.exe：必须让子进程以 node 模式跑，
          // 否则 spawn 出来的是一个新 Electron 应用，SDK 握手永远不完成。
          env: {
            ...process.env,
            ...(process.versions.electron ? { ELECTRON_RUN_AS_NODE: '1' } : {}),
            // headless worker：工具调用自动放行（DSH_PERMISSION_MODE 同时决定 sandbox 与 approval）。
            DSH_PERMISSION_MODE: config.dshPermissionMode,
            SUPER_AGENT_RECALL_INDEX: this.recallIndexPath,
            SUPER_AGENT_RECALL_EXTRA: this.recallExtraPath,
            SUPER_AGENT_JOB_DIR: join(resolve(config.workspace || process.cwd()), '.seed', 'jobs'),
            SUPER_AGENT_WORKSPACE: resolve(config.workspace || process.cwd()),
            SUPER_AGENT_CONTROL_DIR: this.controlDir,
            SUPER_AGENT_DAEMON_URL: config.daemonUrl,
            SUPER_AGENT_DAEMON_TOKEN: config.daemonToken,
            ...(config.daemonEndpointsJson ? { SUPER_AGENT_DAEMONS: config.daemonEndpointsJson } : {}),
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
        ...(config.channelsEnabled ? { channels: this.channelWriter } : {}),
      },
    })
    this.runtime = runtime
    this.speculator = this.buildSpeculator(config)
    this.writeRecallIndex()
    // 重启恢复：上次进程留下的 running assignment 收口，并给工单投递 resume 输入。
    if (config.recoverOnStart) {
      try {
        const recovered = this.runtime.engine.recoverAfterRestart()
        this.lastRecovery = recovered.length
        if (recovered.length > 0) void this.tick()
      } catch (error) {
        console.error('super-agent: recoverAfterRestart failed', String(error))
      }
    }
    const judge = this.buildWatchdogJudge(config)
    const advisor = this.buildWatchdogAdvisor(config)
    this.watchdog = new Watchdog({
      clock,
      staleSeconds: config.staleSeconds,
      ...(judge ? { judge } : {}),
      ...(advisor ? { advisor } : {}),
    })
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
    this.routerSession?.observe(trigger)
    const produced = this.runtime.engine.ingest(trigger)
    if (produced.length > 0) this.maybeSpeculate(trigger)
    return produced.length
  }

  /** 自动投机：只对配置的 Source、且未被 Gate 过滤的事件后台尝试（文章 §3.4）。 */
  private maybeSpeculate(trigger: Trigger): void {
    if (!this.speculator) return
    if (this.runtime.engine.state.dispositions[trigger.id] === 'filtered') return
    const candidate = {
      id: trigger.id,
      source: trigger.source,
      text: trigger.text,
      channelIds: trigger.channelIds,
      threadIds: trigger.threadIds,
    }
    if (!this.speculator.shouldRun(candidate)) return
    void this.speculator.run(candidate).catch((error: unknown) => {
      console.error('super-agent speculation failed', String(error))
    })
  }

  async tick(): Promise<boolean> {
    const before = this.runtime.store.lastSeq()
    this.drainControl()
    await this.runtime.tickUntilIdle()
    this.writeRecallIndex()
    return this.runtime.store.lastSeq() > before
  }

  /** Worker 交回 Router：取消订阅并重新评估该 Thread（Router 可新建工单或忽略）。 */
  handback(ticketId: string, reason = '', drive = true): void {
    this.runtime.engine.handback(ticketId, reason)
    if (drive) void this.tick()
  }

  /** Worker 取消订阅（不重新评估）。 */
  unsubscribe(ticketId: string, threadId?: string, drive = true): void {
    this.runtime.engine.unsubscribe(ticketId, threadId)
    if (drive) void this.tick()
  }

  /** 文件式控制入口：worker 工具写入请求，tick 时统一应用并删除。 */
  private drainControl(): void {
    let files: string[] = []
    try {
      files = readdirSync(this.controlDir).filter((file) => file.endsWith('.json'))
    } catch {
      return
    }
    for (const file of files) {
      const path = join(this.controlDir, file)
      try {
        const request = JSON.parse(readFileSync(path, 'utf8')) as Record<string, unknown>
        const ticketId = typeof request.ticketId === 'string' ? request.ticketId : ''
        if (!ticketId) continue
        const reason = typeof request.reason === 'string' ? request.reason : ''
        if (request.action === 'handback') this.handback(ticketId, reason, false)
        else if (request.action === 'unsubscribe') {
          this.unsubscribe(ticketId, typeof request.threadId === 'string' ? request.threadId : undefined, false)
        } else if (request.action === 'reply') {
          const text = typeof request.text === 'string' ? request.text : ''
          if (text) this.reply(ticketId, text)
        }
      } catch (error) {
        console.error(`super-agent control ${file} failed`, String(error))
      } finally {
        try { unlinkSync(path) } catch { /* already removed */ }
      }
    }
  }

  /** 链式召回：按 trigger/thread/ticket id 取摘要 + 下一跳 handles（模型/Router 共用）。 */
  recallContext(kind: RecallKind, id: string): RecallResult {
    return recall(this.runtime.engine.state, kind, id)
  }

  /** 写召回索引文件：worker 用读取工具按 id 逐跳展开上下文。 */
  writeRecallIndex(): string {
    const state = this.runtime.engine.state
    const triggers: Record<string, unknown> = {}
    for (const trigger of Object.values(state.triggers)) {
      triggers[trigger.id] = {
        source: trigger.source,
        actor: trigger.actor,
        text: trigger.text.slice(0, 2000),
        threadIds: trigger.threadIds,
        channelIds: trigger.channelIds,
        at: trigger.at,
      }
    }
    const threads: Record<string, unknown> = {}
    for (const thread of Object.values(state.threads)) {
      threads[thread.id] = {
        triggerIds: Object.values(state.triggers)
          .filter((trigger) => trigger.threadIds.includes(thread.id))
          .map((trigger) => trigger.id),
        ticketIds: Object.values(state.tickets)
          .filter((ticket) => ticket.threadIds.includes(thread.id))
          .map((ticket) => ticket.id),
      }
    }
    const tickets: Record<string, unknown> = {}
    for (const ticket of Object.values(state.tickets)) {
      const reports = state.reports[ticket.id] ?? []
      tickets[ticket.id] = {
        shortName: ticket.shortName,
        state: ticket.state,
        threadIds: ticket.threadIds,
        channelIds: ticket.channelIds,
        triggerId: ticket.mandate.triggerId,
        reports: reports.slice(-5).map((report) => ({
          status: report.status,
          summary: report.summary.slice(0, 2000),
          at: report.at,
        })),
      }
    }
    mkdirSync(dirname(this.recallIndexPath), { recursive: true })
    writeFileSync(this.recallIndexPath, JSON.stringify({
      writeAt: Math.floor(Date.now() / 1000),
      triggers,
      threads,
      tickets,
    }, null, 1), 'utf8')
    return this.recallIndexPath
  }

  retry(ticketId: string): void {
    this.runtime.engine.retry(ticketId)
  }

  reply(ticketId: string, text: string): void {
    // 全双工：回合进行中的回复不打断 worker，排队等本轮结束后立即处理。
    if (this.sdk?.isRunning(ticketId)) {
      this.sdk.enqueueInput(ticketId, text)
      return
    }
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

  /** 准入策略：本地恒允许；配置了入站的 source 按白名单/mention 规则放行。 */
  private buildPolicy(config: SuperAgentHostConfig): Policy {
    const rules = [{ source: 'local', actor: '*', allow: true, strength: 'explicit' as const, note: 'local-explicit' }]
    const senders: [string, string][] = [['local', '*']]
    if (config.sourceFeishuChatIds.trim()) {
      rules.push({ source: 'feishu', actor: '*', allow: true, strength: 'explicit' as const, note: 'feishu-inbound' })
      for (const actor of splitList(config.sourceFeishuAllowedSenders)) senders.push(['feishu', actor])
    }
    if (config.sourceGithubRepos.trim()) {
      rules.push({ source: 'github', actor: '*', allow: true, strength: 'explicit' as const, note: 'github-inbound' })
      for (const actor of splitList(config.sourceGithubAllowedActors)) senders.push(['github', actor])
    }
    const mentionRequiredFor = splitList(config.sourceMentionRequired)
    const mentionTokens = splitList(config.mentionTokens)
    return buildPolicy(rules, 'auto', senders, {
      ...(mentionRequiredFor.length > 0 ? { mentionRequiredFor } : {}),
      ...(mentionTokens.length > 0 ? { mentionTokens } : {}),
    })
  }

  /** 轮询所有入站 Source：新 Trigger 进引擎并驱动一轮（幂等由 engine 的 trigger id 保证）。 */
  async pollSources(): Promise<void> {
    if (this.runtime.engine.isPaused) return
    for (const source of this.sourceList) {
      try {
        const triggers = await source.poll()
        if (this.failedSources.delete(source.name)) {
          recordSourceRecovery(this.runtime.store, this.runtime.clock, source.name)
        }
        let ingested = 0
        for (const trigger of triggers) ingested += this.ingest(trigger)
        if (ingested > 0) await this.tick()
      } catch (error) {
        if (!this.failedSources.has(source.name)) {
          this.failedSources.add(source.name)
          recordSourceFailure(this.runtime.store, this.runtime.clock, source.name, String(error))
        }
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

  /**
   * 独立 Watchdog 裁定（文章 §6）：主系统之外判断"是否真的在推进、要不要介入"。
   * - llm：host 内联模型调用；
   * - session：独立 DSH runtime 会话（独立工作目录 .seed/watchdog + 独立回合）。
   */
  private buildWatchdogJudge(config: SuperAgentHostConfig): LlmWatchdogJudge | DshWatchdogJudge | undefined {
    if (config.watchdogMode === 'session') {
      if (!this.sdk) return undefined
      return new DshWatchdogJudge(this.sdk, config.workspace || process.cwd())
    }
    if (config.watchdogMode !== 'llm') return undefined
    const apiKey = process.env[config.llmApiKeyEnv]?.trim()
    if (!apiKey) return undefined
    return new LlmWatchdogJudge(createRouterClient({
      baseUrl: config.llmBaseUrl,
      apiKey,
      model: config.llmModel,
      timeoutMs: config.llmTimeoutMs,
    }))
  }

  /** 自然语言运维问答的顾问：session 模式走独立 DSH 会话，llm 模式走内联模型。 */
  private buildWatchdogAdvisor(config: SuperAgentHostConfig): LlmWatchdogAdvisor | DshWatchdogAdvisor | undefined {
    if (config.watchdogMode === 'session') {
      if (!this.sdk) return undefined
      return new DshWatchdogAdvisor(this.sdk, config.workspace || process.cwd())
    }
    if (config.watchdogMode !== 'llm') return undefined
    const apiKey = process.env[config.llmApiKeyEnv]?.trim()
    if (!apiKey) return undefined
    return new LlmWatchdogAdvisor(createRouterClient({
      baseUrl: config.llmBaseUrl,
      apiKey,
      model: config.llmModel,
      timeoutMs: config.llmTimeoutMs,
    }))
  }

  /** 维护者问 Watchdog"卡在哪/为什么"；没有模型时退回确定性摘要。 */
  async askWatchdog(question: string): Promise<string> {
    const text = question.trim()
    if (!text) throw new Error('question required')
    const answer = await this.watchdog.ask(text, this.runtime.engine.state)
    this.lastWatchdogAnswer = { at: Math.floor(Date.now() / 1000), question: text, answer }
    return answer
  }

  /** 投机执行：后台尝试，只有确认有价值才交付（发到 channel）；否则静默丢弃。 */
  async speculate(text: string, channelIds: readonly string[] = []): Promise<{ id: string; delivered: boolean; summary: string }> {
    if (!this.speculator) throw new Error('speculation requires DSH runtime and speculationEnabled')
    const id = `spec-manual-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
    const outcome = await this.speculator.run({ id, source: 'manual', text, channelIds })
    return outcome
      ? { id: outcome.candidateId, delivered: outcome.delivered, summary: outcome.summary }
      : { id, delivered: false, summary: 'skipped (duplicate or concurrency limit)' }
  }

  /** 构造投机执行器：来源策略/去重/并发由 core Speculator 统一，执行由 DSH runtime 完成。 */
  private buildSpeculator(config: SuperAgentHostConfig): Speculator | undefined {
    if (!config.speculationEnabled || !this.sdk) return undefined
    const sdk = this.sdk
    return new Speculator({
      runner: {
        run: async (candidate, signal) => {
          const dir = join(this.ticketsRoot, `spec-${candidate.id}`)
          mkdirSync(dir, { recursive: true })
          const raw = await sdk.runStandalone(this.speculationPrompt(candidate.text, dir), dir)
          if (signal.aborted) return { deliver: false, summary: 'aborted' }
          return parseSpeculationVerdict(raw)
        },
      },
      deliver: async (candidate, verdict) => {
        for (const address of candidate.channelIds) {
          try {
            await this.channelWriter.send(
              { id: `spec-channel-${candidate.id}`, threadId: `spec:${candidate.id}`, address },
              `[投机执行] ${verdict.summary}`,
            )
          } catch (error) {
            console.error('super-agent speculation: channel send failed', address, String(error))
          }
        }
      },
      options: { sources: splitList(config.speculationSources), maxConcurrent: 1, timeoutMs: 300_000 },
    })
  }

  private speculationPrompt(text: string, dir: string): string {
    return [
      '你是 Super-agent 的投机执行 worker：在后台尝试复现并修复，结果有价值才交付，否则保持安静。',
      `工作目录：${dir}`,
      '任务来源事件：',
      text,
      '要求：先在当前目录复现/验证；如果确实确认问题且找到简单修复，deliver=true 并给出可交付结论；',
      '否则 deliver=false，summary 写为何不值得交付。',
      '最后必须只输出一行 JSON：{"deliver":true|false,"summary":"..."}',
    ].join('\n')
  }

  /** 跑一次看门狗巡检；intervene 时对每个 finder 触达的工单 retry 并驱动一轮。 */
  async checkWatchdog(): Promise<WatchdogReport> {
    const report = await this.watchdog.check(this.runtime.engine.state)
    this.lastWatchdog = report
    this.interventions.push({
      at: Math.floor(Date.now() / 1000),
      action: report.verdict.action,
      reason: report.verdict.reason,
      findings: report.findings.length,
    })
    if (this.interventions.length > 20) this.interventions.shift()
    if (report.verdict.action === 'intervene') {
      console.warn(`super-agent watchdog: intervene (${report.verdict.reason}) findings=${report.findings.length}`)
      for (const finding of report.findings) {
        if (!finding.ticketId) continue
        try {
          this.runtime.engine.retry(finding.ticketId)
        } catch (error) {
          // 不可重试的工单（已结束/无派工）不影响其它 finding。
          console.error('super-agent watchdog: retry skipped', finding.ticketId, String(error))
        }
      }
      void this.tick()
      // 介入后持续复查：下一次巡检在 15s 后。
      this.rechecks += 1
      const timer = setTimeout(() => {
        void this.agitate()
      }, 15_000)
      timer.unref()
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
        queuedInputs: this.sdk?.pendingInputs(ticket.id) ?? 0,
        turns: this.sdk?.turnCount(ticket.id) ?? 0,
        stage: stageOf(state, ticket),
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
        ? {
          findings: this.lastWatchdog.findings.length,
          action: this.lastWatchdog.verdict.action,
          reason: this.lastWatchdog.verdict.reason,
          interventions: this.interventions.slice(-3),
          rechecks: this.rechecks,
          lastAsk: this.lastWatchdogAnswer ?? null,
        }
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
      recovery: { events: this.lastRecovery, ticketsDir: this.ticketsRoot },
      speculations: (this.speculator?.outcomes ?? []).slice(-10).map((item) => ({
        id: item.candidateId,
        at: item.at,
        delivered: item.delivered,
        summary: item.summary,
      })),
      speculationStats: this.speculator?.stats() ?? null,
      config: {
        assessorMode: this.assessorMode,
        routerMode: this.routerSession ? 'llm' : 'off',
        watchdogMode: this.watchdogMode,
        sources: this.sourceList.map((source) => source.name),
        speculationEnabled: this.speculationEnabled,
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
      case 'watchdog': {
        if (!input.text) throw new Error('text required')
        reply = await this.askWatchdog(input.text)
        break
      }
      case 'policy': {
        const policyInput = input.policy ?? {}
        const rules = (policyInput.rules ?? []).map((rule) => ({
          source: rule.source,
          actor: rule.actor,
          allow: rule.allow,
          strength: rule.strength ?? ('explicit' as const),
          note: rule.note ?? 'panel',
        }))
        const senders = (policyInput.allowedSenders ?? []).map(
          (pair) => [pair[0], pair[1]] as [string, string],
        )
        this.runtime.engine.setPolicy(
          buildPolicy(rules, policyInput.acceptMode ?? 'auto', senders),
        )
        void this.tick()
        break
      }
      case 'speculate': {
        if (!input.text) throw new Error('text required')
        const outcome = await this.speculate(
          input.text,
          input.channel ? [input.channel] : [],
        )
        reply = outcome.delivered
          ? `已交付：${outcome.summary}`
          : `未交付：${outcome.summary}`
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

/** 解析投机执行 worker 的交付判定（最后一行 JSON）。 */
function parseSpeculationVerdict(raw: string): { deliver: boolean; summary: string } {
  const matches = raw.match(/\{[^{}]*"deliver"[^{}]*\}/g)
  const last = matches?.at(-1)
  if (last) {
    try {
      const parsed = JSON.parse(last) as { deliver?: unknown; summary?: unknown }
      return {
        deliver: parsed.deliver === true,
        summary: typeof parsed.summary === 'string' ? parsed.summary.slice(0, 500) : '',
      }
    } catch {
      // 落到默认：不交付
    }
  }
  return { deliver: false, summary: raw.slice(0, 300) }
}

/** 逗号分隔配置 → 去空白列表。 */
function splitList(value: string): string[] {
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}