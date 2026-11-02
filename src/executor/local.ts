/** 本地执行器：每个工单一个目录、一个 worker 子进程，报告经 stdout JSON 行回收。 */

import { type ChildProcess, execFile, spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { promisify } from "node:util";

import type { Clock } from "../clock.ts";
import { workerBaseEnv } from "../worker_env.ts";
import type { Assignment, Input, Report, ReportStatus, Ticket } from "../domain.ts";
import type { Executor } from "../ports.ts";

const execFileAsync = promisify(execFile);

const STATUSES: ReadonlySet<string> = new Set([
  "progress",
  "waiting",
  "ready",
  "blocked",
  "failed",
  "dropped",
]);

export interface WorkerCommand {
  readonly file: string;
  readonly args?: readonly string[];
}

export interface LocalExecutorOptions {
  /** 执行根目录：每个工单在其下用 shortName 建目录。 */
  readonly root: string;
  /** 每次 Assignment 启动的 worker 命令。 */
  readonly worker: WorkerCommand;
  /** 首次准备命令（如 git worktree），每个工单只跑一次。 */
  readonly prepare?: WorkerCommand;
  /** 报告回收：接到结构化报告后交给引擎（engine.report）。 */
  readonly report: (report: Report) => void;
  readonly clock: Clock;
  readonly env?: Readonly<Record<string, string>>;
  /** 按工单动态追加环境变量（模型配置、执行变量等）。 */
  readonly envFor?: (assignment: Assignment, ticket: Ticket, dir: string) => Record<string, string>;
  /** false = 只透传基础环境，不继承宿主全部变量（生产默认由 App 设为 false）。 */
  readonly inheritEnv?: boolean;
}

export class LocalExecutor implements Executor {
  private readonly options: LocalExecutorOptions;
  private readonly children = new Map<string, ChildProcess>();
  private readonly prepared = new Set<string>();

  constructor(options: LocalExecutorOptions) {
    this.options = options;
  }

  async launch(assignment: Assignment, ticket: Ticket): Promise<void> {
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

  async deliver(ticket: Ticket, input: Input): Promise<void> {
    const child = this.children.get(ticket.id);
    if (!this.isLive(child)) return; // worker 已退出：下次派工会带上新输入
    const stdin = child.stdin;
    stdin.on("error", () => undefined);
    stdin.write(`${JSON.stringify({ inputId: input.id, kind: input.kind, ref: input.ref })}\n`, () => undefined);
  }

  private isLive(child: ChildProcess | undefined): child is ChildProcess & { stdin: NonNullable<ChildProcess["stdin"]> } {
    return child !== undefined && child.exitCode === null && !child.killed && child.stdin !== null && !child.stdin.destroyed;
  }

  async stop(assignment: Assignment): Promise<void> {
    this.children.get(assignment.ticketId)?.kill();
  }

  /** 关闭所有 worker（进程退出/测试清理用）。 */
  closeAll(): void {
    for (const child of this.children.values()) child.kill();
    this.children.clear();
  }

  private onLine(line: string, assignment: Assignment, ticket: Ticket): void {
    const raw = line.trim();
    if (!raw) return;
    let payload: { status?: unknown; summary?: unknown };
    try {
      payload = JSON.parse(raw) as { status?: unknown; summary?: unknown };
    } catch {
      return; // 非结构化输出忽略
    }
    const status = typeof payload.status === "string" ? payload.status : "";
    if (!STATUSES.has(status)) return;
    this.options.report({
      ticketId: ticket.id,
      assignmentId: assignment.id,
      status: status as ReportStatus,
      summary: typeof payload.summary === "string" ? payload.summary.slice(0, 2000) : "",
      at: this.options.clock.now(),
    });
  }

  private environment(
    assignment: Assignment,
    ticket: Ticket,
    dir: string,
  ): Record<string, string> {
    return {
      ...(this.options.inheritEnv === false ? workerBaseEnv() : process.env),
      ...this.options.env,
      ...(this.options.envFor ? this.options.envFor(assignment, ticket, dir) : {}),
      DSH_SUPERAGENT_DIR: dir,
      DSH_SUPERAGENT_NAME: ticket.shortName,
      DSH_SUPERAGENT_TICKET: ticket.id,
      DSH_SUPERAGENT_ASSIGNMENT: assignment.id,
      DSH_SUPERAGENT_SCOPE: ticket.mandate.scope,
    } as Record<string, string>;
  }
}