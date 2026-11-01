import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { GhCliClient } from "../src/sources/github_cli.ts";

/** 用真实子进程模拟 gh：按参数返回 GitHub API 形状的 JSON。 */
function fixture(): { command: string; prefix: string[]; calls: string; cleanup: () => void } {
  const dir = mkdtempSync(join(tmpdir(), "seed-gh-"));
  const script = join(dir, "gh-fixture.mjs");
  writeFileSync(
    script,
    `import { appendFileSync } from "node:fs";
appendFileSync(${JSON.stringify(join(dir, "calls.log"))}, process.argv.slice(2).join(" ") + "\\n");
const args = process.argv.slice(2);
if (args.includes("/notifications")) {
  process.stdout.write(JSON.stringify([
    { id: "1", reason: "review_requested", updated_at: "2026-11-01T10:00:00Z",
      subject: { title: "修复登录", type: "PullRequest", url: "https://api.github.com/repos/o/r/pulls/42" },
      repository: { full_name: "o/r" } },
    { id: "2", reason: "mention", updated_at: "2026-11-01T11:00:00Z",
      subject: { title: "一个 issue", type: "Issue", url: "https://api.github.com/repos/o/r/issues/7" },
      repository: { full_name: "o/r" } }
  ]));
} else {
  process.stdout.write(JSON.stringify({ id: 99 }));
}
`,
  );
  return { command: process.execPath, prefix: [script], calls: join(dir, "calls.log"), cleanup: () => rmDir(dir) };
}

function rmDir(dir: string): void {
  rmSync(dir, { recursive: true, force: true });
}

test("GhCliClient：解析通知并映射为 Trigger 可用的结构", async () => {
  const fx = fixture();
  const client = new GhCliClient({ command: fx.command, argsPrefix: fx.prefix });
  const notifications = await client.listNotifications();

  assert.equal(notifications.length, 2);
  assert.deepEqual(notifications[0], {
    id: "1",
    repo: "o/r",
    number: 42,
    kind: "PullRequest",
    title: "修复登录",
    reason: "review_requested",
    actor: "github",
    updatedAt: Math.floor(Date.parse("2026-11-01T10:00:00Z") / 1000),
  });
  assert.equal(notifications[1]?.kind, "Issue");
  assert.equal(notifications[1]?.number, 7);
  fx.cleanup();
});

test("GhCliClient：评论走 gh api POST", async () => {
  const fx = fixture();
  const client = new GhCliClient({ command: fx.command, argsPrefix: fx.prefix });
  const result = await client.createComment("o/r", 42, "已完成");
  assert.equal(result.id, "99");
  fx.cleanup();
});

test("GhCliClient：命令失败时抛错（由 runner 记 Source 失败）", async () => {
  const client = new GhCliClient({ command: process.execPath, argsPrefix: ["-e", "process.exit(4)"] });
  await assert.rejects(client.listNotifications());
});