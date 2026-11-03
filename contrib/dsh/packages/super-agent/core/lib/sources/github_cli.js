/** GitHub 客户端（gh CLI 真实调用）。要求本机 `gh auth login` 已完成。 */
import { execFile } from "node:child_process";
import { promisify } from "node:util";
const execFileAsync = promisify(execFile);
export class GhCliClient {
    command;
    argsPrefix;
    timeoutMs;
    cwd;
    excludeSelf;
    login;
    constructor(options = {}) {
        this.command = options.command ?? "gh";
        this.argsPrefix = [...(options.argsPrefix ?? [])];
        this.timeoutMs = options.timeoutMs ?? 60_000;
        this.cwd = options.cwd;
        this.excludeSelf = options.excludeSelf ?? true;
    }
    async listNotifications() {
        const stdout = await this.gh([
            "api",
            "/notifications",
            "-H",
            "Accept: application/vnd.github+json",
            "--paginate",
        ]);
        const payload = JSON.parse(stdout);
        const items = Array.isArray(payload[0]) ? payload.flat() : payload;
        const self = this.excludeSelf ? await this.selfLogin() : "";
        const result = [];
        for (const item of items) {
            const mapped = this.toNotification(item);
            if (!mapped)
                continue;
            if (self) {
                const commentUrl = item.subject?.latest_comment_url;
                if (commentUrl) {
                    const author = await this.commentAuthor(commentUrl).catch(() => "");
                    if (author === self)
                        continue; // 自己刚发的评论，不再触发新任务
                }
            }
            result.push(mapped);
        }
        return result;
    }
    async selfLogin() {
        if (this.login !== undefined)
            return this.login;
        try {
            this.login = (await this.gh(["api", "/user", "--jq", ".login"])).trim();
        }
        catch {
            this.login = "";
        }
        return this.login;
    }
    async commentAuthor(url) {
        const path = url.replace(/^https?:\/\/api\.github\.com\//, "");
        return (await this.gh(["api", path, "--jq", ".user.login"])).trim();
    }
    async createComment(repo, number, body) {
        const stdout = await this.gh([
            "api",
            `repos/${repo}/issues/${number}/comments`,
            "-X",
            "POST",
            "-f",
            `body=${body}`,
        ]);
        const parsed = JSON.parse(stdout);
        return { id: String(parsed.id ?? "") };
    }
    toNotification(item) {
        const repo = item.repository?.full_name;
        const url = item.subject?.url ?? "";
        const numberMatch = /(?:issues|pulls)\/(\d+)$/.exec(url);
        if (!repo || !numberMatch)
            return null;
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
    async gh(args) {
        const { stdout } = await execFileAsync(this.command, [...this.argsPrefix, ...args], {
            timeout: this.timeoutMs,
            windowsHide: true,
            ...(this.cwd ? { cwd: this.cwd } : {}),
            maxBuffer: 8 * 1024 * 1024,
        });
        return stdout;
    }
}
//# sourceMappingURL=github_cli.js.map