/**
 * 文档信道（文章 §4.2）：把结构化交付写成 Markdown，供人直接阅读或归档。
 * 同一地址的多次更新追加到同一文档，保留时间线。
 */
import { appendFileSync, existsSync, mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { SystemClock } from "../clock.js";
export class DocsChannel {
    dir;
    clock;
    constructor(dir, clock = new SystemClock()) {
        this.dir = resolve(dir);
        this.clock = clock;
    }
    async send(channel, text) {
        mkdirSync(this.dir, { recursive: true });
        const name = safeName(channel.address.replace(/^docs:/, "") || channel.id);
        const file = join(this.dir, `${name}.md`);
        const stamp = new Date(this.clock.now() * 1000).toISOString();
        const header = existsSync(file) ? "" : `# ${name}\n\n`;
        appendFileSync(file, `${header}## ${stamp}\n\n${text.trim()}\n\n`, "utf8");
    }
}
function safeName(value) {
    return value.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "document";
}
//# sourceMappingURL=docs.js.map