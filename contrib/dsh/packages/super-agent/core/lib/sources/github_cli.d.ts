/** GitHub 客户端（gh CLI 真实调用）。要求本机 `gh auth login` 已完成。 */
import type { GithubClient, GithubNotification } from "./github.ts";
export interface GhCliOptions {
    /** gh 可执行文件（默认 gh；测试可传 node + fixture 脚本）。 */
    readonly command?: string;
    readonly argsPrefix?: readonly string[];
    readonly timeoutMs?: number;
    readonly cwd?: string;
    /** 跳过"最新评论作者是自己"的通知，避免 agent 自己的回复形成回环（默认开）。 */
    readonly excludeSelf?: boolean;
}
export declare class GhCliClient implements GithubClient {
    private readonly command;
    private readonly argsPrefix;
    private readonly timeoutMs;
    private readonly cwd;
    private readonly excludeSelf;
    private login;
    constructor(options?: GhCliOptions);
    listNotifications(): Promise<GithubNotification[]>;
    private selfLogin;
    private commentAuthor;
    createComment(repo: string, number: number, body: string): Promise<{
        id: string;
    }>;
    private toNotification;
    private gh;
}
