import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { DocsChannel } from "../src/channels/docs.ts";
import { EmailDraftChannel } from "../src/channels/email.ts";
import { FakeClock } from "../src/clock.ts";
import type { Channel } from "../src/domain.ts";
import { compactForIm, formatForChannel, structureForAsync } from "../src/format.ts";
import * as h from "./helpers.ts";

function channel(address: string): Channel {
  return { ...h.channel(), address };
}

test("IM 规范：去 Markdown 且不超过 100 字", () => {
  const text = `## 结论\n\n**已完成**：修复了 [登录问题](https://example.com)，${"很长的说明".repeat(40)}`;
  const compact = compactForIm(text);
  assert.ok(compact.length <= 101, `got ${compact.length}`);
  assert.ok(!compact.includes("**"));
  assert.ok(!compact.includes("]("));
});

test("异步信道使用结构化交付", () => {
  for (const address of ["gh:o/r#1", "docs:report", "mailto:a@b.c"]) {
    const formatted = formatForChannel(address, "修复完成");
    assert.equal(formatted, structureForAsync("修复完成"));
    assert.match(formatted, /### 结论/);
  }
  assert.equal(formatForChannel("local:cli", "好的"), "好的");
  const long = `## 结论\n\n${"完整报告内容。".repeat(50)}`;
  assert.equal(formatForChannel("fs:oc_123", long), long.trim());
  assert.equal(formatForChannel("feishu:oc_123", long), long.trim());
});

test("DocsChannel：同一地址追加到同一文档", async () => {
  const dir = mkdtempSync(join(tmpdir(), "seed-docs-"));
  try {
    const clock = new FakeClock();
    const channelWriter = new DocsChannel(dir, clock);
    await channelWriter.send(channel("docs:release-notes"), "## 第一版\n内容 A");
    clock.advance(60);
    await channelWriter.send(channel("docs:release-notes"), "## 第二版\n内容 B");
    const files = readdirSync(dir);
    assert.deepEqual(files, ["release-notes.md"]);
    const body = readFileSync(join(dir, files[0] as string), "utf8");
    assert.match(body, /内容 A/);
    assert.match(body, /内容 B/);
    assert.equal(body.match(/^## \d{4}-/gm)?.length, 2);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("EmailDraftChannel：产出标准 .eml 草稿且不覆盖", async () => {
  const dir = mkdtempSync(join(tmpdir(), "seed-mail-"));
  try {
    const clock = new FakeClock();
    const channelWriter = new EmailDraftChannel(dir, clock);
    await channelWriter.send(channel("mailto:alice@example.com"), "会议改期\n周三下午三点可以吗？");
    await channelWriter.send(channel("mailto:alice@example.com"), "补充\n附带议程。");
    const files = readdirSync(dir);
    assert.equal(files.length, 2);
    const mail = readFileSync(join(dir, files[0] as string), "utf8");
    assert.match(mail, /To: alice@example.com/);
    assert.match(mail, /Subject: 会议改期/);
    assert.match(mail, /周三下午三点可以吗/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});