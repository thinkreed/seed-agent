/** 本地执行器：每个工单一个目录、一个 worker 子进程，报告经 stdout JSON 行回收。 */
import { execFile, spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { promisify } from "node:util";
import { workerBaseEnv } from "../worker_env.js";
const execFileAsync = promisify(execFile);
const STATUSES = new Set([
    "progress",
    "waiting",
    "ready",
    "blocked",
    "failed",
    "dropped",
]);
export class LocalExecutor {
    options;
    children = new Map();
    prepared = new Set();
    constructor(options) {
        this.options = options;
    }
    async launch(assignment, ticket) {
        const dir = join(this.options.root, ticket.shortName);
        mkdirSync(dir, { recursive: true });
        const env = this.environment(assignment, ticket, dir);
        if (this.options.prepare && !this.prepared.has(ticket.id)) {
            const prepare = this.options.prepare;
            await execFileAsync(prepare.file, [...(prepare.args ?? [])], { cwd: dir, env });
            this.prepared.add(ticket.id);
        }
        const child = spawn(this.options.worker.file, [...(this.options.worker.args ?? [])], {
            cwd: dir,
            env,
            stdio: ["pipe", "pipe", "pipe"],
        });
        this.children.set(ticket.id, child);
        child.on("exit", () => this.children.delete(ticket.id));
        if (child.stdout) {
            createInterface({ input: child.stdout }).on("line", (line) => this.onLine(line, assignment, ticket));
        }
    }
    async deliver(ticket, input) {
        const child = this.children.get(ticket.id);
        if (!this.isLive(child))
            return; // worker 已退出：下次派工会带上新输入
        const stdin = child.stdin;
        stdin.on("error", () => undefined);
        stdin.write(`${JSON.stringify({ inputId: input.id, kind: input.kind, ref: input.ref })}\n`, () => undefined);
    }
    isLive(child) {
        return child !== undefined && child.exitCode === null && !child.killed && child.stdin !== null && !child.stdin.destroyed;
    }
    async stop(assignment) {
        this.children.get(assignment.ticketId)?.kill();
    }
    /** 关闭所有 worker（进程退出/测试清理用）。 */
    closeAll() {
        for (const child of this.children.values())
            child.kill();
        this.children.clear();
    }
    onLine(line, assignment, ticket) {
        const raw = line.trim();
        if (!raw)
            return;
        let payload;
        try {
            payload = JSON.parse(raw);
        }
        catch {
            return; // 非结构化输出忽略
        }
        const status = typeof payload.status === "string" ? payload.status : "";
        if (!STATUSES.has(status))
            return;
        this.options.report({
            ticketId: ticket.id,
            assignmentId: assignment.id,
            status: status,
            summary: typeof payload.summary === "string" ? payload.summary.slice(0, 2000) : "",
            at: this.options.clock.now(),
        });
    }
    environment(assignment, ticket, dir) {
        return {
            ...(this.options.inheritEnv === false ? workerBaseEnv() : process.env),
            ...this.options.env,
            ...(this.options.envFor ? this.options.envFor(assignment, ticket, dir) : {}),
            DSH_SUPERAGENT_DIR: dir,
            DSH_SUPERAGENT_NAME: ticket.shortName,
            DSH_SUPERAGENT_TICKET: ticket.id,
            DSH_SUPERAGENT_ASSIGNMENT: assignment.id,
            DSH_SUPERAGENT_SCOPE: ticket.mandate.scope,
        };
    }
}
//# sourceMappingURL=local.js.map