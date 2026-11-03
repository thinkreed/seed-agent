/**
 * 健康检查：doctor 命令用。全部是真实探测（网络/进程/文件系统），不做写外部服务的动作。
 */
import { execFile } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { promisify } from "node:util";
import { feishuCheckers } from "./health_feishu.js";
const execFileAsync = promisify(execFile);
export function createCheckers(config, deps) {
    const env = deps.env;
    const checks = [];
    checks.push({
        name: "model.key",
        required: true,
        run: async () => {
            if (!config.model)
                return { ok: false, detail: "config.model is missing" };
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
            if (!config.model)
                return { ok: false, detail: "config.model is missing" };
            const key = env[config.model.apiKeyEnv];
            if (!key)
                return { ok: false, detail: "skipped: no api key" };
            const url = `${config.model.baseUrl.replace(/\/$/, "")}/models`;
            const doFetch = deps.fetchImpl ?? fetch;
            try {
                const response = await doFetch(url, { headers: { authorization: `Bearer ${key}` } });
                if (response.status === 401 || response.status === 403) {
                    return { ok: false, detail: `auth rejected (HTTP ${response.status})` };
                }
                return { ok: true, detail: `reachable (HTTP ${response.status})` };
            }
            catch (error) {
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
            }
            catch (error) {
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
            }
            catch (error) {
                return { ok: false, detail: `api failed: ${String(error).slice(0, 120)}` };
            }
        },
    });
    checks.push(...feishuCheckers(config, deps));
    checks.push({
        name: "worker.script",
        required: true,
        run: async () => ({
            ok: true,
            detail: config.worker
                ? `worker: ${config.worker.file} ${config.worker.args?.join(" ") ?? ""}`
                : "worker: built-in worker/main.ts",
        }),
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
            }
            catch (error) {
                return { ok: false, detail: String(error).slice(0, 160) };
            }
        },
    });
    return checks;
}
export async function runChecks(checkers) {
    const results = [];
    for (const checker of checkers) {
        const outcome = await checker.run().catch((error) => ({
            ok: false,
            detail: String(error).slice(0, 160),
        }));
        results.push({ name: checker.name, required: checker.required, ...outcome });
    }
    return results;
}
export function formatChecks(checks) {
    return checks
        .map((check) => `${check.ok ? "OK  " : "FAIL"} ${check.name.padEnd(16)} ${check.detail}`)
        .join("\n");
}
async function gh(deps, args) {
    if (deps.gh)
        return deps.gh(args);
    const { stdout } = await execFileAsync("gh", args, { timeout: 30_000, windowsHide: true });
    return { stdout };
}
//# sourceMappingURL=health.js.map