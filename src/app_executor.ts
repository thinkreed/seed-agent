/** 执行器装配：本地 LocalExecutor，或远端 daemon（HttpTransport + RemoteExecutor）。 */

import { join, resolve } from "node:path";

import type { Clock } from "./clock.ts";
import type { SeedConfig } from "./config.ts";
import type { Executor } from "./ports.ts";
import type { Runtime } from "./runtime.ts";
import type { WorkerSpec } from "./executor/protocol.ts";
import { LocalExecutor } from "./executor/local.ts";
import { HttpTransport } from "./executor/http.ts";
import { RemoteExecutor } from "./executor/remote.ts";

export interface AppExecutorOptions {
  readonly config: SeedConfig;
  readonly workerCommand?: WorkerSpec;
  readonly clock: Clock;
  readonly runtime: () => Runtime;
  readonly apiKey: string;
  readonly recallPath: string;
  readonly controlPath: string;
  readonly env: Readonly<Record<string, string | undefined>>;
}

export interface AppExecutor {
  readonly executor: Executor;
  close(): void;
}

export function buildAppExecutor(options: AppExecutorOptions): AppExecutor {
  const { config, clock } = options;
  const worker = options.workerCommand ?? {
    file: process.execPath,
    args: [join(import.meta.dirname, "worker", "main.ts")],
  };
  if (config.remote) {
    const remote = new RemoteExecutor({
      transport: new HttpTransport({
        url: config.remote.url,
        ...(config.remote.tokenEnv ? { token: options.env[config.remote.tokenEnv] ?? "" } : {}),
        onReconnect: () => {
          // 设备重新上线：重拉 assignment 并补投未确认输入（文章 §5.2）。
          void remote.recover().catch(() => undefined);
        },
      }),
      clock,
      report: (report) => options.runtime().engine.report(report),
      worker: config.worker ?? worker,
      ...(config.prepare ? { prepare: config.prepare } : {}),
      recallIndexPath: options.recallPath,
    });
    return { executor: remote, close: () => remote.closeAll() };
  }
  const local = new LocalExecutor({
    root: resolve(config.workRoot),
    worker,
    clock,
    inheritEnv: false,
    report: (report) => options.runtime().engine.report(report),
    envFor: (assignment, ticket, dir) => {
      const state = options.runtime().store.state();
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
        SEED_RECALL_INDEX: options.recallPath,
        SEED_CONTROL_DIR: options.controlPath,
        SEED_MODEL_BASE_URL: config.model?.baseUrl ?? "",
        SEED_MODEL_API_KEY: options.apiKey,
        SEED_MODEL_NAME: config.model?.name ?? "",
      };
    },
  });
  return { executor: local, close: () => local.closeAll() };
}