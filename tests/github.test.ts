import assert from "node:assert/strict";
import { test } from "node:test";

import { FakeClock } from "../src/clock.ts";
import {
  GitHubChannel,
  GitHubSource,
  parseThreadAddress,
  threadAddress,
  type GithubClient,
  type GithubNotification,
} from "../src/sources/github.ts";

class FakeGithub implements GithubClient {
  notifications: GithubNotification[] = [];
  readonly comments: { repo: string; number: number; body: string }[] = [];
  failNotifications = false;

  async listNotifications(): Promise<GithubNotification[]> {
    if (this.failNotifications) throw new Error("api down");
    return [...this.notifications];
  }

  async createComment(repo: string, number: number, body: string): Promise<{ id: string }> {
    this.comments.push({ repo, number, body });
    return { id: `c-${this.comments.length}` };
  }
}

function note(overrides: Partial<GithubNotification> = {}): GithubNotification {
  return {
    id: "n-1",
    repo: "thinkreed/seed-agent",
    number: 42,
    kind: "PullRequest",
    title: "修复登录 500",
    reason: "review_requested",
    actor: "alice",
    updatedAt: 1_700_000_100,
    ...overrides,
  };
}

test("threadAddress / parseThreadAddress：地址可逆", () => {
  const address = threadAddress("o/r", 7);
  assert.equal(address, "gh:o/r#7");
  assert.deepEqual(parseThreadAddress(address), { repo: "o/r", number: 7 });
  assert.throws(() => parseThreadAddress("bad"), /bad github thread address/);
});

test("GitHubSource：通知 -> Trigger，一条 PR 一个线程", async () => {
  const client = new FakeGithub();
  client.notifications = [note(), note({ number: 43, updatedAt: 1_700_000_200, title: "第二个" })];
  const source = new GitHubSource({ client, clock: new FakeClock() });
  const triggers = await source.poll();

  assert.equal(triggers.length, 2);
  assert.equal(triggers[0]?.threadIds[0], "gh:thinkreed/seed-agent#42");
  assert.equal(triggers[0]?.source, "github");
  assert.match(triggers[0]?.text ?? "", /PullRequest/);
  assert.ok((triggers[0]?.at ?? 0) <= (triggers[1]?.at ?? 0));
});

test("GitHubSource：按仓库与 reason 过滤", async () => {
  const client = new FakeGithub();
  client.notifications = [
    note(),
    note({ repo: "other/repo" }),
    note({ reason: "subscribed", number: 44 }),
  ];
  const source = new GitHubSource({
    client,
    clock: new FakeClock(),
    repos: ["thinkreed/seed-agent"],
    reasons: ["review_requested"],
  });
  const triggers = await source.poll();
  assert.equal(triggers.length, 1);
  assert.equal(triggers[0]?.id, "gh:thinkreed/seed-agent#42:1700000100");
});

test("GitHubSource：重复轮询产生同样的 id（引擎侧幂等）", async () => {
  const client = new FakeGithub();
  client.notifications = [note()];
  const source = new GitHubSource({ client, clock: new FakeClock() });
  const first = await source.poll();
  const second = await source.poll();
  assert.deepEqual(first.map((item) => item.id), second.map((item) => item.id));
});

test("GitHubChannel：把回复写到对应 Issue/PR", async () => {
  const client = new FakeGithub();
  const channel = new GitHubChannel(client);
  await channel.send({ address: "gh:o/r#9" }, "已完成，请 review");
  assert.deepEqual(client.comments, [{ repo: "o/r", number: 9, body: "已完成，请 review" }]);
});

test("GitHubChannel：地址非法时抛错（由 effects 退避）", async () => {
  const channel = new GitHubChannel(new FakeGithub());
  await assert.rejects(channel.send({ address: "nope" }, "x"));
});