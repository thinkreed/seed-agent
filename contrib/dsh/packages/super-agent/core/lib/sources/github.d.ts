/** GitHub Source：把通知/评审请求转成 Trigger，一条 Issue/PR = 一个 Thread。 */
import type { Clock } from "../clock.ts";
import type { Trigger } from "../domain.ts";
import type { Source } from "../ports.ts";
export interface GithubNotification {
    readonly id: string;
    readonly repo: string;
    readonly number: number;
    readonly kind: "Issue" | "PullRequest";
    readonly title: string;
    readonly reason: string;
    readonly actor: string;
    /** epoch 秒；客户端负责把平台时间转换过来。 */
    readonly updatedAt: number;
}
export interface GithubClient {
    listNotifications(): Promise<GithubNotification[]>;
    createComment(repo: string, number: number, body: string): Promise<{
        id: string;
    }>;
}
export interface GitHubSourceOptions {
    readonly client: GithubClient;
    readonly clock: Clock;
    /** 只关心这些仓库（owner/name）；空表示全部。 */
    readonly repos?: readonly string[];
    /** 只关心这些 reason；空表示全部。 */
    readonly reasons?: readonly string[];
}
export declare function threadAddress(repo: string, number: number): string;
export declare function parseThreadAddress(address: string): {
    repo: string;
    number: number;
};
export declare class GitHubSource implements Source {
    readonly name = "github";
    private readonly options;
    constructor(options: GitHubSourceOptions);
    poll(): Promise<Trigger[]>;
    private accepts;
}
/** GitHub 写侧：把回复发到对应 Issue/PR 的评论里。 */
export declare class GitHubChannel {
    private readonly client;
    constructor(client: GithubClient);
    send(channel: {
        address: string;
    }, text: string): Promise<void>;
}
