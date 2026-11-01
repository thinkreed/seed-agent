/**
 * 真实验收脚本：用产品代码（GhCliClient + GitHubChannel）在真实 issue/PR 上发评论。
 *
 * 用法：node scripts/live_github_comment.ts <owner/repo> <number> <text...>
 * 之后会用 gh api 读回最新评论做校验。
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";

import { GitHubChannel } from "../src/sources/github.ts";
import { GhCliClient } from "../src/sources/github_cli.ts";

const execFileAsync = promisify(execFile);

const [repo, numberRaw, ...textParts] = process.argv.slice(2);
const number = Number(numberRaw);
const text = textParts.join(" ");

if (!repo || !Number.isInteger(number) || number <= 0 || !text) {
  console.error("usage: node scripts/live_github_comment.ts <owner/repo> <number> <text>");
  process.exit(2);
}

const client = new GhCliClient();
const channel = new GitHubChannel(client);
console.log(`posting to ${repo}#${number} ...`);
await channel.send({ address: `gh:${repo}#${number}` }, text);

const { stdout } = await execFileAsync(
  "gh",
  ["api", `repos/${repo}/issues/${number}/comments`, "--jq", ".[-1] | {id, user: .user.login, body}"],
  { windowsHide: true },
);
const latest = JSON.parse(stdout) as { id: number; user: string; body: string };
console.log(`verified latest comment: id=${latest.id} user=${latest.user}`);
console.log(`body: ${latest.body.slice(0, 120)}`);
if (!latest.body.includes(text.slice(0, 20))) {
  console.error("FAIL: comment text mismatch");
  process.exit(1);
}
console.log("GITHUB COMMENT OK");