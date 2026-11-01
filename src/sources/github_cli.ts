/** GitHub 客户端（gh CLI 真实调用）。要求本机 `gh auth login` 已完成。 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";

import type { GithubClient, GithubNotification } from "./github.ts";

const execFileAsync = promisify(execFile);

export interface GhCliOptions {
  /** gh 可执行文件（默认 gh；测试可传 node + fixture 脚本）。 */
  readonly command?: string;
  readonly argsPrefix?: readonly string[];
  readonly timeoutMs?: number;
  readonly cwd?: string;
}

interface NotificationPayload {
  readonly id?: string;
  readonly reason?: string;
  readonly updated_at?: string;
  readonly subject?: { readonly title?: string; readonly type?: string; readonly url?: string };
  readonly repository?: { readonly full_name?: string };
}

export class GhCliClient implements GithubClient {
  private readonly command: string;
  private readonly argsPrefix: string[];
  private readonly timeoutMs: number;
  private readonly cwd: string | undefined;

  constructor(options: GhCliOptions = {}) {
    this.command = options.command ?? "gh";
    this.argsPrefix = [...(options.argsPrefix ?? [])];
    this.timeoutMs = options.timeoutMs ?? 60_000;
    this.cwd = options.cwd;
  }

  async listNotifications(): Promise<GithubNotification[]> {
    const stdout = await this.gh([
      "api",
      "/notifications",
      "-H",
      "Accept: application/vnd.github+json",
      "--paginate",
    ]);
    const payload = JSON.parse(stdout) as NotificationPayload[] | NotificationPayload[][];
    const items = Array.isArray(payload[0]) ? (payload as NotificationPayload[][]).flat() : (payload as NotificationPayload[]);
    return items
      .map((item) => this.toNotification(item))
      .filter((item): item is GithubNotification => item !== null);
  }

  async createComment(repo: string, number: number, body: string): Promise<{ id: string }> {
    const stdout = await this.gh([
      "api",
      `repos/${repo}/issues/${number}/comments`,
      "-X",
      "POST",
      "-f",
      `body=${body}`,
    ]);
    const parsed = JSON.parse(stdout) as { id?: number | string };
    return { id: String(parsed.id ?? "") };
  }

  private toNotification(item: NotificationPayload): GithubNotification | null {
    const repo = item.repository?.full_name;
    const url = item.subject?.url ?? "";
    const numberMatch = /(?:issues|pulls)\/(\d+)$/.exec(url);
    if (!repo || !numberMatch) return null;
    const kind = item.subject?.type === "PullRequest" ? "PullRequest" : "Issue";
    return {
      id: item.id ?? `${repo}#${numberMatch[1]}`,
      repo,
      number: Number(numberMatch[1]),
      kind,
      title: item.subject?.title ?? "",
      reason: item.reason ?? "unknown",
      actor: "github",
      updatedAt: Math.floor(Date.parse(item.updated_at ?? "") / 1000) || 0,
    };
  }

  private async gh(args: string[]): Promise<string> {
    const { stdout } = await execFileAsync(this.command, [...this.argsPrefix, ...args], {
      timeout: this.timeoutMs,
      windowsHide: true,
      ...(this.cwd ? { cwd: this.cwd } : {}),
      maxBuffer: 8 * 1024 * 1024,
    });
    return stdout;
  }
}