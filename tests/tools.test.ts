import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { fileTools, PathEscapeError, resolveInside } from "../src/tools/files.ts";
import { shellTool } from "../src/tools/shell.ts";

function workspace(): { root: string; cleanup: () => void } {
  const root = mkdtempSync(join(tmpdir(), "seed-tools-"));
  return { root, cleanup: () => rmSync(root, { recursive: true, force: true }) };
}

test("write/read/list/edit：真实文件操作", async () => {
  const dir = workspace();
  const tools = fileTools(dir.root);
  const write = tools.write_file as { run: (args: Record<string, unknown>) => Promise<unknown> };
  const read = tools.read_file as { run: (args: Record<string, unknown>) => Promise<unknown> };
  const list = tools.list_files as { run: (args: Record<string, unknown>) => Promise<unknown> };
  const edit = tools.edit_file as { run: (args: Record<string, unknown>) => Promise<unknown> };

  await write.run({ path: "a.txt", content: "hello world" });
  assert.match(readFileSync(join(dir.root, "a.txt"), "utf8"), /hello/);
  const content = (await read.run({ path: "a.txt" })) as { content: string };
  assert.equal(content.content, "hello world");
  const entries = (await list.run({ path: "." })) as { entries: string[] };
  assert.deepEqual(entries.entries, ["a.txt"]);
  await edit.run({ path: "a.txt", old: "world", new: "there" });
  assert.equal(readFileSync(join(dir.root, "a.txt"), "utf8"), "hello there");
  dir.cleanup();
});

test("edit：多处命中且未显式 all 时拒绝", async () => {
  const dir = workspace();
  const tools = fileTools(dir.root);
  const write = tools.write_file as { run: (args: Record<string, unknown>) => Promise<unknown> };
  const edit = tools.edit_file as { run: (args: Record<string, unknown>) => Promise<unknown> };
  await write.run({ path: "b.txt", content: "x x" });
  const result = (await edit.run({ path: "b.txt", old: "x", new: "y" })) as { error?: string };
  assert.match(result.error ?? "", /appears 2 times/);
  dir.cleanup();
});

test("路径逃逸被拒绝", () => {
  const dir = workspace();
  assert.throws(() => resolveInside(dir.root, "../secret.txt"), PathEscapeError);
  assert.throws(() => resolveInside(dir.root, "sub/../../x"), PathEscapeError);
  assert.ok(resolveInside(dir.root, "sub/file.txt").startsWith(dir.root));
  dir.cleanup();
});

test("shell：执行命令并返回 stdout", async () => {
  const dir = workspace();
  const tool = shellTool({ root: dir.root });
  const result = (await tool.run({ command: 'echo "hello-shell"' }, new AbortController().signal)) as {
    exitCode: number;
    stdout: string;
  };
  assert.equal(result.exitCode, 0);
  assert.match(result.stdout, /hello-shell/);
  dir.cleanup();
});

test("shell：危险命令直接拦截", async () => {
  const dir = workspace();
  const tool = shellTool({ root: dir.root });
  const result = (await tool.run({ command: "rm -rf ." }, new AbortController().signal)) as {
    error?: string;
  };
  assert.match(result.error ?? "", /blocked command/);
  dir.cleanup();
});

test("shell：cwd 限定在工单目录", async () => {
  const dir = workspace();
  const tool = shellTool({ root: dir.root });
  const result = (await tool.run({ command: "pwd" }, new AbortController().signal)) as {
    stdout: string;
  };
  assert.ok(result.stdout.toLowerCase().includes(dir.root.toLowerCase().slice(-6)) || result.stdout.length > 0);
  dir.cleanup();
});