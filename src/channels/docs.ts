/**
 * 文档信道（文章 §4.2）：把结构化交付写成 Markdown，供人直接阅读或归档。
 * 同一地址的多次更新追加到同一文档，保留时间线。
 */

import { appendFileSync, existsSync, mkdirSync } from "node:fs";
import { join, resolve } from "node:path";

import type { Clock } from "../clock.ts";
import { SystemClock } from "../clock.ts";
import type { Channel } from "../domain.ts";
import type { ChannelWriter } from "../ports.ts";

export class DocsChannel implements ChannelWriter {
  private readonly dir: string;
  private readonly clock: Clock;

  constructor(dir: string, clock: Clock = new SystemClock()) {
    this.dir = resolve(dir);
    this.clock = clock;
  }

  async send(channel: Channel, text: string): Promise<void> {
    mkdirSync(this.dir, { recursive: true });
    const name = safeName(channel.address.replace(/^docs:/, "") || channel.id);
    const file = join(this.dir, `${name}.md`);
    const stamp = new Date(this.clock.now() * 1000).toISOString();
    const header = existsSync(file) ? "" : `# ${name}\n\n`;
    appendFileSync(file, `${header}## ${stamp}\n\n${text.trim()}\n\n`, "utf8");
  }
}

function safeName(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "document";
}