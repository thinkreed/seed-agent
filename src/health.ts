/**
 * 健康检查：doctor 命令用。全部是真实探测（网络/进程/文件系统），不做写外部服务的动作。
 */

import { execFile } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { promisify } from "node:util";

import type { SeedConfig } from "./config.ts";

const execFileAsync = promisify(execFile);

export interface HealthCheck {
  readonly name: string;
  readonly required: boolean;
  readonly ok: boolean;
  readonly detail: string;
}

export interface Checker {
  readonly name: string;
  readonly required: boolean;
  run(): Promise<{ ok: boolean; detail: string }>;
}

export interface CheckDeps {
  readonly env: Readonly<Record<string, string | undefined>>;
  /** 覆盖 gh 调用（测试用）。 */
  readonly gh?: (args: string[]) => Promise<{ stdout: string }>;
  /** 覆盖 HTTP 探测（测试用）。 */
  readonly fetchImpl?: typeof fetch;
}

export function createCheckers(config: SeedConfig, deps: CheckDeps): Checker[] {
  const env = deps.env;
  const checks: Checker[] = [];

  checks.push({
    name: "model.key",
    required: true,
    run: async () => {
      if (!config.model) return { ok: false, detail: "config.model is missing" };
      const value = env[config.model.apiKeyEnv];
      return value
        ? { ok: true, detail: `${config.model.apiKeyEnv} present (${value.length} chars)` }
        : { ok: false, detail: `missing env ${config.model.apiKeyEnv}` };
    },
  });

  checks.push({
    name: "model.endpoint",
    required: true,
    run: async () => {
      if (!config.model) return { ok: false, detail: "config.model is missing" };
      const key = env[config.model.apiKeyEnv];
      if (!key) return { ok: false, detail: "skipped: no api key" };
      const url = `${config.model.baseUrl.replace(/\/$/, "")}/models`;
      const doFetch = deps.fetchImpl ?? fetch;
      try {
        const response = await doFetch(url, {
          headers: { authorization: `Bearer ${key}` },
        });
        if (response.status === 401 || response.status === 403) {
          return { ok: false, detail: `auth rejected (HTTP ${response.status})` };
        }
        return { ok: true, detail: `reachable (HTTP ${response.status})` };
      } catch (error) {
        return { ok: false, detail: `unreachable: ${String(error).slice(0, 120)}` };
      }
    },
  });

  checks.push({
    name: "github.auth",
    required: true,
    run: async () => {
      try {
        const { stdout } = await gh(deps, ["auth", "status"]);
        const account = /account (\S+)/.exec(stdout)?.[1] ?? "unknown";
        return { ok: true, detail: `logged in as ${account}` };
      } catch (error) {
        return { ok: false, detail: `gh auth failed: ${String(error).slice(0, 120)}` };
      }
    },
  });

  checks.push({
    name: "github.identity",
    required: false,
    run: async () => {
      try {
        const { stdout } = await gh(deps, ["api", "/user", "--jq", ".login"]);
        return { ok: true, detail: `api user: ${stdout.trim()}` };
      } catch (error) {
        return { ok: false, detail: `api failed: ${String(error).slice(0, 120)}` };
      }
    },
  });

  if (config.sources?.feishu) {
    const feishu = config.sources.feishu;
    checks.push({
      name: "feishu.token",
      required: true,
      run: async () => {
        const appId = env[feishu.appIdEnv];
        const secret = env[feishu.appSecretEnv];
        if (!appId || !secret) return { ok: false, detail: `missing ${feishu.appIdEnv}/${feishu.appSecretEnv}` };
        const doFetch = deps.fetchImpl ?? fetch;
        try {
          const response = await doFetch(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ app_id: appId, app_secret: secret }),
            },
          );
          const payload = (await response.json()) as { tenant_access_token?: string; code?: number };
          return payload.tenant_access_token
            ? { ok: true, detail: `token ok (code ${String(payload.code ?? 0)})` }
            : { ok: false, detail: `token missing (code ${String(payload.code)})` };
        } catch (error) {
          return { ok: false, detail: `unreachable: ${String(error).slice(0, 120)}` };
        }
      },
    });
  }

  checks.push({
    name: "worker.script",
    required: true,
    run: async () => {
      const path = config.worker?.file ?? process.execPath;
      return path && path.length > 0
        ? { ok: true, detail: `worker: ${config.worker ? `${config.worker.file} ${config.worker.args?.join(" ") ?? ""}` : "built-in worker/main.ts"}` }
        : { ok: false, detail: "no worker configured" };
    },
  });

  checks.push({
    name: "fs.writable",
    required: true,
    run: async () => {
      const dirs = [dirname(resolve(config.dbPath)), resolve(config.workRoot)];
      try {
        for (const dir of dirs) {
          mkdirSync(dir, { recursive: true });
          const probe = mkdtempSync(join(tmpdir(), "seed-doctor-"));
          writeFileSync(join(probe, "ok"), "1");
          rmSync(probe, { recursive: true, force: true });
        }
        return { ok: true, detail: dirs.join(", ") };
      } catch (error) {
        return { ok: false, detail: String(error).slice(0, 160) };
      }
    },
  });

  return checks;
}

export async function runChecks(checkers: readonly Checker[]): Promise<HealthCheck[]> {
  const results: HealthCheck[] = [];
  for (const checker of checkers) {
    const outcome = await checker.run().catch((error: unknown) => ({
      ok: false,
      detail: String(error).slice(0, 160),
    }));
    results.push({ name: checker.name, required: checker.required, ...outcome });
  }
  return results;
}

export function formatChecks(checks: readonly HealthCheck[]): string {
  return checks
    .map((check) => `${check.ok ? "OK  " : "FAIL"} ${check.name.padEnd(16)} ${check.detail}`)
    .join("\n");
}

async function gh(deps: CheckDeps, args: string[]): Promise<{ stdout: string }> {
  if (deps.gh) return deps.gh(args);
  const { stdout } = await execFileAsync("gh", args, { timeout: 30_000, windowsHide: true });
  return { stdout };
}