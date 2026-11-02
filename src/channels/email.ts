/**
 * 邮件草稿信道（文章 §4.2）：个人助手场景下先起草结构化邮件，再由人确认发送。
 * 不直接连 SMTP：产物是标准 .eml 草稿，避免凭据进入模型上下文。
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

import type { Clock } from "../clock.ts";
import { SystemClock } from "../clock.ts";
import type { Channel } from "../domain.ts";
import type { ChannelWriter } from "../ports.ts";

export class EmailDraftChannel implements ChannelWriter {
  private readonly dir: string;
  private readonly clock: Clock;
  private counter = 0;

  constructor(dir: string, clock: Clock = new SystemClock()) {
    this.dir = resolve(dir);
    this.clock = clock;
  }

  async send(channel: Channel, text: string): Promise<void> {
    mkdirSync(this.dir, { recursive: true });
    const to = channel.address.replace(/^(mailto|email):/, "") || channel.id;
    const [subjectLine, ...rest] = text.trim().split("\n");
    this.counter += 1;
    const stamp = this.clock.now();
    const file = join(this.dir, `${safeName(to)}-${Math.floor(stamp)}-${this.counter}.eml`);
    const headers = [
      `To: ${to}`,
      `Subject: ${(subjectLine ?? "").slice(0, 120)}`,
      `Date: ${new Date(stamp * 1000).toUTCString()}`,
      "MIME-Version: 1.0",
      'Content-Type: text/plain; charset="utf-8"',
      "",
      rest.join("\n").trim() || text.trim(),
      "",
    ];
    writeFileSync(file, headers.join("\r\n"), "utf8");
  }
}

function safeName(value: string): string {
  return value.replace(/[^a-zA-Z0-9._@-]+/g, "-").replace(/^-+|-+$/g, "") || "mail";
}