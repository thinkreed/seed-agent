/** GitHub Source：把通知/评审请求转成 Trigger，一条 Issue/PR = 一个 Thread。 */

import type { Clock } from "../clock.ts";
import type { Trigger } from "../domain.ts";
import type { Source } from "../ports.ts";

export interface GithubNotification {
  readonly id: string;
  readonly repo: string; // owner/name
  readonly number: number;
  readonly kind: "Issue" | "PullRequest";
  readonly title: string;
  readonly reason: string; // mention | review_requested | comment | ...
  readonly actor: string;
  /** epoch 秒；客户端负责把平台时间转换过来。 */
  readonly updatedAt: number;
}

export interface GithubClient {
  listNotifications(): Promise<GithubNotification[]>;
  createComment(repo: string, number: number, body: string): Promise<{ id: string }>;
}

export interface GitHubSourceOptions {
  readonly client: GithubClient;
  readonly clock: Clock;
  /** 只关心这些仓库（owner/name）；空表示全部。 */
  readonly repos?: readonly string[];
  /** 只关心这些 reason；空表示全部。 */
  readonly reasons?: readonly string[];
}

export function threadAddress(repo: string, number: number): string {
  return `gh:${repo}#${number}`;
}

export function parseThreadAddress(address: string): { repo: string; number: number } {
  const match = /^gh:([^#]+)#(\d+)$/.exec(address);
  if (!match) throw new Error(`bad github thread address: ${address}`);
  return { repo: match[1] as string, number: Number(match[2]) };
}

export class GitHubSource implements Source {
  readonly name = "github";
  private readonly options: GitHubSourceOptions;

  constructor(options: GitHubSourceOptions) {
    this.options = options;
  }

  async poll(): Promise<Trigger[]> {
    const notifications = await this.options.client.listNotifications();
    return notifications
      .filter((item) => this.accepts(item))
      .map((item) => ({
        id: `gh:${item.repo}#${item.number}:${item.updatedAt}`,
        source: "github",
        actor: item.actor,
        text: `[${item.kind}] ${item.title} (${item.reason})`,
        threadIds: [threadAddress(item.repo, item.number)],
        channelIds: [threadAddress(item.repo, item.number)],
        at: item.updatedAt,
      }))
      .sort((a, b) => a.at - b.at || a.id.localeCompare(b.id));
  }

  private accepts(item: GithubNotification): boolean {
    const repos = this.options.repos;
    if (repos && repos.length > 0 && !repos.includes(item.repo)) return false;
    const reasons = this.options.reasons;
    if (reasons && reasons.length > 0 && !reasons.includes(item.reason)) return false;
    return true;
  }
}

/** GitHub 写侧：把回复发到对应 Issue/PR 的评论里。 */
export class GitHubChannel {
  private readonly client: GithubClient;

  constructor(client: GithubClient) {
    this.client = client;
  }

  async send(channel: { address: string }, text: string): Promise<void> {
    const { repo, number } = parseThreadAddress(channel.address);
    await this.client.createComment(repo, number, text);
  }
}