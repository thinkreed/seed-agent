/**
 * 应用装配：把真实组件接成可运行系统（无 fake）。
 * 需要真实凭证：
 *   - 模型：环境变量（默认 DEEPSEEK_API_KEY）
 *   - GitHub：`gh auth login` 已完成
 *   - 飞书：FEISHU_APP_ID / FEISHU_APP_SECRET（配置里可改名）
 */

import { join, resolve } from "node:path";

import { ConsoleChannel } from "./channels/console.ts";
import { CompositeChannel } from "./channels/composite.ts";
import { SystemClock } from "./clock.ts";
import type { SeedConfig } from "./config.ts";
import { loadEnvFile } from "./env.ts";
import { WatchdogController } from "./control.ts";
import { Daemon } from "./daemon.ts";
import { LocalExecutor } from "./executor/local.ts";
import { LlmAssessor } from "./assessor_llm.ts";
import { OpenAIClient } from "./llm/openai.ts";
import { Router, TemplateComposer } from "./router.ts";
import { Runtime } from "./runtime.ts";
import { SourceRunner } from "./runner.ts";
import { FeishuChannel, FeishuSource } from "./sources/feishu.ts";
import { FeishuHttpClient } from "./sources/feishu_http.ts";
import { GitHubChannel, GitHubSource } from "./sources/github.ts";
import { GhCliClient } from "./sources/github_cli.ts";
import { JsonlInboxSource } from "./sources/jsonl.ts";
import { Watchdog } from "./watchdog.ts";
import { LlmWatchdogJudge } from "./watchdog_llm.ts";

export class AppError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AppError";
  }
}

export interface AppOptions {
  readonly config: SeedConfig;
  readonly env?: Readonly<Record<string, string | undefined>>;
  readonly once?: boolean;
  /** 覆盖 worker 命令（默认用内置 worker 进程）。 */
  readonly workerCommand?: { file: string; args: readonly string[] };
  /** 额外 env 文件（默认读 .env）。 */
  readonly envFile?: string;
}

function resolveEnv(overrides: AppOptions["env"], envFile: string): Record<string, string | undefined> {
  const merged: Record<string, string | undefined> = { ...process.env };
  loadEnvFile(envFile, merged);
  return { ...merged, ...(overrides ?? {}) };
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
    const env = resolveEnv(options.env, options.envFile ?? process.env.SEED_ENV_FILE ?? ".env");
    const config = options.config;
    if (!config.model) throw new AppError("config.model is required for real runs");
    const apiKey = env[config.model.apiKeyEnv];
    if (!apiKey) throw new AppError(`missing env ${config.model.apiKeyEnv} for model access`);

    const clock = new SystemClock();
    const modelClient = new OpenAIClient({
      baseUrl: config.model.baseUrl,
      apiKey,
      model: config.model.name,
      ...(config.model.temperature === undefined ? {} : { temperature: config.model.temperature }),
      ...(config.model.maxTokens === undefined ? {} : { maxTokens: config.model.maxTokens }),
    });
    const assessor = new LlmAssessor(modelClient);

    const routes: { prefix: string; writer: import("./ports.ts").ChannelWriter }[] = [
      { prefix: "local", writer: new ConsoleChannel("[seed:local]") },
      { prefix: "gh:", writer: new GitHubChannel(new GhCliClient()) },
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
      sources.push(new FeishuSource(client));
      routes.push({ prefix: "fs:", writer: new FeishuChannel(client) });
    }
    if (sources.length === 0) throw new AppError("config.sources is empty: configure local/github/feishu");

    const channels = new CompositeChannel(routes);
    let runtime: Runtime;
    const worker = options.workerCommand ?? {
      file: process.execPath,
      args: [join(import.meta.dirname, "worker", "main.ts")],
    };
    const executor = new LocalExecutor({
      root: resolve(config.workRoot),
      worker,
      clock,
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
          SEED_MODEL_BASE_URL: config.model?.baseUrl ?? "",
          SEED_MODEL_API_KEY: apiKey,
          SEED_MODEL_NAME: config.model?.name ?? "",
        };
      },
    });

    runtime = Runtime.build({
      assessor,
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
    const watchdog = new Watchdog({ clock, staleSeconds: config.staleSeconds, judge: new LlmWatchdogJudge(modelClient) });
    const controller = new WatchdogController(runtime.engine);
    const runner = new SourceRunner({ sources, engine: runtime.engine, store: runtime.store, clock });
    const daemon = new Daemon({
      runner,
      engine: runtime.engine,
      store: runtime.store,
      clock,
      intervalMs: config.intervalMs,
      watchdog: { check: (state) => watchdog.check(state), apply: (report) => controller.apply(report) },
      afterRound: async () => {
        router.queueReplies();
        await runtime.engine.tick();
      },
    });

    return new App(runtime, daemon, router, executor);
  }

  /** 跑一轮并收敛（单次模式/验证用）。 */
  async runOnce(): Promise<void> {
    await this.daemon.runRound();
    await this.runtime.tickUntilIdle();
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