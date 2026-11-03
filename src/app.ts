/**
 * 应用装配：把真实组件接成可运行系统（无 fake）。
 * 需要真实凭证：
 *   - 模型：环境变量（默认 DEEPSEEK_API_KEY）
 *   - GitHub：`gh auth login` 已完成
 *   - 飞书：FEISHU_APP_ID / FEISHU_APP_SECRET（配置里可改名）
 */

import { dirname, join, resolve } from "node:path";
import { AppError } from "./app_error.ts";
import { buildAppSpeculation } from "./app_speculation.ts";
import { ConsoleChannel } from "./channels/console.ts";
import { CompositeChannel } from "./channels/composite.ts";
import { DocsChannel } from "./channels/docs.ts";
import { EmailDraftChannel } from "./channels/email.ts";
import { SystemClock } from "./clock.ts";
import type { SeedConfig } from "./config.ts";
import { mergeEnv } from "./env.ts";
import { WatchdogController } from "./control.ts";
import { Daemon } from "./daemon.ts";
import { LocalExecutor } from "./executor/local.ts";
import { buildAssessor } from "./assessor_router.ts";
import { writeRecallIndex } from "./recall_index.ts";
import { createModelClient } from "./model_client.ts";
import { Router, TemplateComposer } from "./router.ts";
import { Runtime } from "./runtime.ts";
import { SourceRunner } from "./runner.ts";
import { FeishuChannel, FeishuSource } from "./sources/feishu.ts";
import { FeishuHttpClient } from "./sources/feishu_http.ts";
import { GitHubChannel, GitHubSource } from "./sources/github.ts";
import { GhCliClient } from "./sources/github_cli.ts";
import { JsonlInboxSource } from "./sources/jsonl.ts";
import { Watchdog } from "./watchdog.ts";
import { LlmWatchdogAdvisor, LlmWatchdogJudge } from "./watchdog_llm.ts";

export { AppError } from "./app_error.ts";
export interface AppOptions {
  readonly config: SeedConfig;
  readonly env?: Readonly<Record<string, string | undefined>>;
  readonly once?: boolean;
  /** 覆盖 worker 命令（默认用内置 worker 进程）。 */
  readonly workerCommand?: { file: string; args: readonly string[] };
  /** 额外 env 文件（默认依次读 seed.env、.env）。 */
  readonly envFile?: string;
}
export class App {
  readonly runtime: Runtime;
  readonly daemon: Daemon;
  readonly router: Router;
  private readonly executor: LocalExecutor;
  private constructor(runtime: Runtime, daemon: Daemon, router: Router, executor: LocalExecutor) {
    this.runtime = runtime;
    this.daemon = daemon;
    this.router = router;
    this.executor = executor;
  }
  static create(options: AppOptions): App {
    const env = mergeEnv(options.env, options.envFile ?? process.env.SEED_ENV_FILE);
    const config = options.config;
    if (!config.model) throw new AppError("config.model is required for real runs");
    const apiKey = env[config.model.apiKeyEnv];
    if (!apiKey) throw new AppError(`missing env ${config.model.apiKeyEnv} for model access`);

    const clock = new SystemClock();
    const recallPath = join(dirname(resolve(config.dbPath)), "recall-index.json");
    const routerConfig = config.routerModel ?? config.model;
    const routerKey = env[routerConfig.apiKeyEnv] ?? apiKey;
    const modelClient = createModelClient(routerConfig, routerKey);
    const assessorBundle = buildAssessor(config, modelClient, () => runtime.engine.state);

    const routes: { prefix: string; writer: import("./ports.ts").ChannelWriter }[] = [
      { prefix: "local", writer: new ConsoleChannel("[seed:local]") },
      { prefix: "gh:", writer: new GitHubChannel(new GhCliClient()) },
      { prefix: "docs:", writer: new DocsChannel(join(config.workRoot, "docs"), clock) },
      { prefix: "mailto:", writer: new EmailDraftChannel(join(config.workRoot, "outbox"), clock) },
      { prefix: "email:", writer: new EmailDraftChannel(join(config.workRoot, "outbox"), clock) },
    ];

    const sources: import("./ports.ts").Source[] = [];
    if (config.sources?.local) sources.push(new JsonlInboxSource(resolve(config.sources.local.inbox)));
    if (config.sources?.github) {
      sources.push(
        new GitHubSource({
          client: new GhCliClient(),
          clock,
          ...(config.sources.github.repos ? { repos: config.sources.github.repos } : {}),
          ...(config.sources.github.reasons ? { reasons: config.sources.github.reasons } : {}),
        }),
      );
    }
    if (config.sources?.feishu) {
      const feishu = config.sources.feishu;
      const appId = env[feishu.appIdEnv];
      const appSecret = env[feishu.appSecretEnv];
      if (!appId || !appSecret) {
        throw new AppError(`missing env ${feishu.appIdEnv} / ${feishu.appSecretEnv} for feishu`);
      }
      const client = new FeishuHttpClient({ appId, appSecret, chatIds: feishu.chatIds });
      sources.push(
        new FeishuSource(client, {
          now: () => clock.now(),
          ...(feishu.sinceSeconds === undefined ? {} : { sinceSeconds: feishu.sinceSeconds }),
        }),
      );
      routes.push({ prefix: "fs:", writer: new FeishuChannel(client) });
    }
    if (sources.length === 0) throw new AppError("config.sources is empty: configure local/github/feishu");

    const channels = new CompositeChannel(routes);
    const speculation = buildAppSpeculation({ model: modelClient, channels, clock, root: join(resolve(config.workRoot), "_speculation"), sources: config.speculationSources ?? [] });
    let runtime: Runtime;
    const worker = options.workerCommand ?? {
      file: process.execPath,
      args: [join(import.meta.dirname, "worker", "main.ts")],
    };
    const executor = new LocalExecutor({
      root: resolve(config.workRoot),
      worker,
      clock,
      inheritEnv: false,
      report: (report) => runtime.engine.report(report),
      envFor: (assignment, ticket, dir) => {
        const state = runtime.store.state();
        const origin = state.triggers[ticket.mandate.triggerId];
        const inputs = Object.values(state.inputs)
          .filter((input) => input.ticketId === ticket.id)
          .map((input) => ({
            id: input.id,
            source: "router",
            actor: "router",
            text: input.ref,
            threadIds: [],
            channelIds: [],
            at: input.at,
          }));
        const initial = origin
          ? [{ ...origin, threadIds: [...origin.threadIds], channelIds: [...origin.channelIds] }]
          : inputs;
        return {
          SEED_WORKER_ROOT: dir,
          SEED_WORKER_TICKET: ticket.id,
          SEED_WORKER_SHORT_NAME: ticket.shortName,
          SEED_WORKER_SCOPE: ticket.mandate.scope,
          SEED_WORKER_ASSIGNMENT: assignment.id,
          SEED_WORKER_INPUT: JSON.stringify(initial),
          SEED_RECALL_INDEX: recallPath,
          SEED_MODEL_BASE_URL: config.model?.baseUrl ?? "",
          SEED_MODEL_API_KEY: apiKey,
          SEED_MODEL_NAME: config.model?.name ?? "",
        };
      },
    });

    runtime = Runtime.build({
      assessor: assessorBundle.assessor,
      executor,
      config: {
        dbPath: resolve(config.dbPath),
        slots: config.slots,
        policy: config.policy,
        channels,
      },
      clock,
    });

    const router = new Router({ store: runtime.store, clock, effects: runtime.engine.effects, composer: new TemplateComposer() });
    const watchdog = new Watchdog({ clock, staleSeconds: config.staleSeconds, judge: new LlmWatchdogJudge(modelClient), advisor: new LlmWatchdogAdvisor(modelClient) });
    const controller = new WatchdogController(runtime.engine);
    const runner = new SourceRunner({ sources, engine: runtime.engine, store: runtime.store, clock, onTrigger: (trigger) => assessorBundle.router?.observe(trigger), onIngested: speculation?.onTrigger });
    const daemon = new Daemon({
      runner,
      engine: runtime.engine,
      store: runtime.store,
      clock,
      intervalMs: config.intervalMs,
      watchdog: { check: (state) => watchdog.check(state), apply: (report) => controller.apply(report) },
      afterRound: async () => {
        writeRecallIndex(runtime.engine.state, recallPath, clock.now());
        router.queueReplies();
        await runtime.engine.tick();
      },
    });

    return new App(runtime, daemon, router, executor);
  }

  /** 跑一轮并等到系统收敛（单次模式/验证用）。 */
  async runOnce(timeoutMs = 600_000): Promise<void> {
    const deadline = this.runtime.clock.now() + timeoutMs / 1000;
    while (this.runtime.clock.now() < deadline) {
      await this.daemon.runRound();
      await this.runtime.tickUntilIdle();
      if (this.runtime.isSettled()) return;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    throw new AppError(`runOnce timed out after ${timeoutMs}ms`);
  }

  /** 常驻运行。 */
  async run(): Promise<void> {
    this.runtime.engine.recoverAfterRestart();
    await this.daemon.run();
  }

  stop(): void {
    this.daemon.stop();
    this.executor.closeAll();
    this.runtime.close();
  }
}