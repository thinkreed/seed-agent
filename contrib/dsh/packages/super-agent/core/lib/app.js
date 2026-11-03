/**
 * 应用装配：把真实组件接成可运行系统（无 fake）。
 * 需要真实凭证：
 *   - 模型：环境变量（默认 DEEPSEEK_API_KEY）
 *   - GitHub：`gh auth login` 已完成
 *   - 飞书：FEISHU_APP_ID / FEISHU_APP_SECRET（配置里可改名）
 */
import { dirname, join, resolve } from "node:path";
import { AppError } from "./app_error.js";
import { buildAppSpeculation } from "./app_speculation.js";
import { ConsoleChannel } from "./channels/console.js";
import { CompositeChannel } from "./channels/composite.js";
import { DocsChannel } from "./channels/docs.js";
import { EmailDraftChannel } from "./channels/email.js";
import { SystemClock } from "./clock.js";
import { mergeEnv } from "./env.js";
import { WatchdogController } from "./control.js";
import { Daemon } from "./daemon.js";
import { buildAppExecutor } from "./app_executor.js";
import { buildAssessor } from "./assessor_router.js";
import { writeRecallIndex } from "./recall_index.js";
import { createModelClient } from "./model_client.js";
import { Router, TemplateComposer } from "./router.js";
import { Runtime } from "./runtime.js";
import { SourceRunner } from "./runner.js";
import { FeishuChannel, FeishuSource } from "./sources/feishu.js";
import { FeishuHttpClient } from "./sources/feishu_http.js";
import { GitHubChannel, GitHubSource } from "./sources/github.js";
import { GhCliClient } from "./sources/github_cli.js";
import { JsonlInboxSource } from "./sources/jsonl.js";
import { Watchdog } from "./watchdog.js";
import { LlmWatchdogAdvisor, LlmWatchdogJudge } from "./watchdog_llm.js";
export { AppError } from "./app_error.js";
export class App {
    runtime;
    daemon;
    router;
    executor;
    closeExecutor;
    constructor(runtime, daemon, router, executor, closeExecutor) {
        this.runtime = runtime;
        this.daemon = daemon;
        this.router = router;
        this.executor = executor;
        this.closeExecutor = closeExecutor;
    }
    static create(options) {
        const env = mergeEnv(options.env, options.envFile ?? process.env.SEED_ENV_FILE);
        const config = options.config;
        if (!config.model)
            throw new AppError("config.model is required for real runs");
        const apiKey = env[config.model.apiKeyEnv];
        if (!apiKey)
            throw new AppError(`missing env ${config.model.apiKeyEnv} for model access`);
        const clock = new SystemClock();
        const recallPath = join(dirname(resolve(config.dbPath)), "recall-index.json");
        const routerConfig = config.routerModel ?? config.model;
        const routerKey = env[routerConfig.apiKeyEnv] ?? apiKey;
        const modelClient = createModelClient(routerConfig, routerKey);
        const assessorBundle = buildAssessor(config, modelClient, () => runtime.engine.state);
        const routes = [
            { prefix: "local", writer: new ConsoleChannel("[seed:local]") },
            { prefix: "gh:", writer: new GitHubChannel(new GhCliClient()) },
            { prefix: "docs:", writer: new DocsChannel(join(config.workRoot, "docs"), clock) },
            { prefix: "mailto:", writer: new EmailDraftChannel(join(config.workRoot, "outbox"), clock) },
            { prefix: "email:", writer: new EmailDraftChannel(join(config.workRoot, "outbox"), clock) },
        ];
        const sources = [];
        if (config.sources?.local)
            sources.push(new JsonlInboxSource(resolve(config.sources.local.inbox)));
        if (config.sources?.github) {
            sources.push(new GitHubSource({
                client: new GhCliClient(),
                clock,
                ...(config.sources.github.repos ? { repos: config.sources.github.repos } : {}),
                ...(config.sources.github.reasons ? { reasons: config.sources.github.reasons } : {}),
            }));
        }
        if (config.sources?.feishu) {
            const feishu = config.sources.feishu;
            const appId = env[feishu.appIdEnv];
            const appSecret = env[feishu.appSecretEnv];
            if (!appId || !appSecret) {
                throw new AppError(`missing env ${feishu.appIdEnv} / ${feishu.appSecretEnv} for feishu`);
            }
            const client = new FeishuHttpClient({ appId, appSecret, chatIds: feishu.chatIds });
            sources.push(new FeishuSource(client, {
                now: () => clock.now(),
                ...(feishu.sinceSeconds === undefined ? {} : { sinceSeconds: feishu.sinceSeconds }),
            }));
            routes.push({ prefix: "fs:", writer: new FeishuChannel(client) });
        }
        if (sources.length === 0)
            throw new AppError("config.sources is empty: configure local/github/feishu");
        const channels = new CompositeChannel(routes);
        const speculation = buildAppSpeculation({ model: modelClient, channels, clock, root: join(resolve(config.workRoot), "_speculation"), sources: config.speculationSources ?? [] });
        let runtime;
        const { executor, close: closeExecutor } = buildAppExecutor({
            config,
            ...(options.workerCommand ? { workerCommand: options.workerCommand } : {}),
            clock,
            runtime: () => runtime,
            apiKey,
            recallPath,
            env,
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
        return new App(runtime, daemon, router, executor, closeExecutor);
    }
    /** 跑一轮并等到系统收敛（单次模式/验证用）。 */
    async runOnce(timeoutMs = 600_000) {
        const deadline = this.runtime.clock.now() + timeoutMs / 1000;
        while (this.runtime.clock.now() < deadline) {
            await this.daemon.runRound();
            await this.runtime.tickUntilIdle();
            if (this.runtime.isSettled())
                return;
            await new Promise((resolve) => setTimeout(resolve, 500));
        }
        throw new AppError(`runOnce timed out after ${timeoutMs}ms`);
    }
    /** 常驻运行。 */
    async run() {
        this.runtime.engine.recoverAfterRestart();
        await this.daemon.run();
    }
    stop() {
        this.daemon.stop();
        this.closeExecutor();
        this.runtime.close();
    }
}
//# sourceMappingURL=app.js.map