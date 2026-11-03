/** 独立 Watchdog 进程：只读事件库、独立模型会话，定时判断并落事件。 */

import { SystemClock } from "./clock.ts";
import { loadConfig } from "./config.ts";
import { WatchdogController } from "./control.ts";
import { Engine } from "./engine.ts";
import { loadDefaultEnv } from "./env.ts";
import { SeqIds } from "./ids.ts";
import { createModelClient } from "./model_client.ts";
import { stateIds } from "./state_ids.ts";
import { SqliteStore } from "./store.ts";
import { Watchdog } from "./watchdog.ts";
import { LlmWatchdogAdvisor, LlmWatchdogJudge } from "./watchdog_llm.ts";

const noopExecutor = {
  launch: async () => undefined,
  deliver: async () => undefined,
  stop: async () => undefined,
};

const noopAssessor = {
  assess: async () => ({
    kind: "ignore" as const,
    strength: "explicit" as const,
    reason: "watchdog-process",
    scope: "ticket" as const,
    rules: [],
  }),
};

export async function watchdogServe(configPath: string, intervalMs = 60_000): Promise<number> {
  const config = loadConfig(configPath);
  const env: Record<string, string | undefined> = { ...process.env };
  loadDefaultEnv(env);
  const modelConfig = config.routerModel ?? config.model;
  if (!modelConfig) throw new Error("config.model is required for watchdog");
  const apiKey = env[modelConfig.apiKeyEnv];
  if (!apiKey) throw new Error(`missing env ${modelConfig.apiKeyEnv}`);
  const clock = new SystemClock();
  const store = new SqliteStore(config.dbPath);
  const ids = new SeqIds([...stateIds(store.state()), ...store.outboxIds()]);
  const engine = new Engine({
    store,
    clock,
    ids,
    assessor: noopAssessor,
    executor: noopExecutor,
    policy: null,
    slots: 0,
  });
  const model = createModelClient(modelConfig, apiKey);
  const watchdog = new Watchdog({
    clock,
    staleSeconds: config.staleSeconds,
    judge: new LlmWatchdogJudge(model),
    advisor: new LlmWatchdogAdvisor(model),
  });
  const controller = new WatchdogController(engine);
  let stopped = false;
  const stop = () => {
    stopped = true;
  };
  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
  try {
    while (!stopped) {
      try {
        const report = await watchdog.check(store.state());
        controller.apply(report);
        console.log(JSON.stringify({ at: clock.now(), findings: report.findings.length, action: report.verdict.action }));
      } catch (error) {
        console.error(`watchdog tick failed: ${String(error)}`);
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
  } finally {
    store.close();
  }
  return 0;
}