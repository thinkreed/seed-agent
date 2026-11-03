/** GitHub Source：把通知/评审请求转成 Trigger，一条 Issue/PR = 一个 Thread。 */
export function threadAddress(repo, number) {
    return `gh:${repo}#${number}`;
}
export function parseThreadAddress(address) {
    const match = /^gh:([^#]+)#(\d+)$/.exec(address);
    if (!match)
        throw new Error(`bad github thread address: ${address}`);
    return { repo: match[1], number: Number(match[2]) };
}
export class GitHubSource {
    name = "github";
    options;
    constructor(options) {
        this.options = options;
    }
    async poll() {
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
    accepts(item) {
        const repos = this.options.repos;
        if (repos && repos.length > 0 && !repos.includes(item.repo))
            return false;
        const reasons = this.options.reasons;
        if (reasons && reasons.length > 0 && !reasons.includes(item.reason))
            return false;
        return true;
    }
}
/** GitHub 写侧：把回复发到对应 Issue/PR 的评论里。 */
export class GitHubChannel {
    client;
    constructor(client) {
        this.client = client;
    }
    async send(channel, text) {
        const { repo, number } = parseThreadAddress(channel.address);
        await this.client.createComment(repo, number, text);
    }
}
//# sourceMappingURL=github.js.map