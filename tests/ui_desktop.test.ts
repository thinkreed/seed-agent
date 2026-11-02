import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import type { ChildProcess } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { browserArgs, findBrowser, openDesktopWindow } from "../src/ui/desktop.ts";

test("browserArgs：Windows 使用 --app 独立窗口模式", () => {
  const args = browserArgs("http://127.0.0.1:4780/", { url: "http://127.0.0.1:4780/", windowSize: "1200,800" }, "C:/tmp/profile");
  if (process.platform === "win32") {
    assert.ok(args.includes("--app=http://127.0.0.1:4780/"));
    assert.ok(args.includes("--window-size=1200,800"));
    assert.ok(args.some((arg) => arg.startsWith("--user-data-dir=")));
  } else {
    assert.deepEqual(args, ["http://127.0.0.1:4780/"]);
  }
});

test("findBrowser：SEED_BROWSER 覆盖优先", () => {
  const found = findBrowser({ SEED_BROWSER: process.execPath });
  assert.equal(found?.file, process.execPath);
});

test("openDesktopWindow：拼装命令、等待退出、可关闭", async () => {
  const dir = mkdtempSync(join(tmpdir(), "seed-desktop-"));
  const calls: { file: string; args: readonly string[] }[] = [];
  const child = new EventEmitter() as EventEmitter & {
    pid?: number;
    exitCode: number | null;
    kill: () => void;
  };
  child.pid = 4242;
  child.exitCode = null;
  child.kill = () => {
    child.exitCode = 0;
    child.emit("exit", 0, null);
  };

  const window = openDesktopWindow({
    url: "http://127.0.0.1:4780/",
    profileDir: dir,
    browser: { file: "C:/Edge/msedge.exe", args: ["--no-first-run"] },
    spawnImpl: ((file: string, args: readonly string[]) => {
      calls.push({ file, args });
      return child as unknown as ChildProcess;
    }) as never,
  });

  assert.equal(window.pid, 4242);
  assert.equal(calls.length, 1);
  assert.equal(calls[0]?.file, "C:/Edge/msedge.exe");
  assert.ok(calls[0]?.args.includes("--no-first-run"));
  if (process.platform === "win32") {
    assert.ok(calls[0]?.args.some((arg) => arg.startsWith("--app=http://127.0.0.1:4780/")));
  }

  const exited = window.waitForExit();
  window.close();
  await exited;
  rmSync(dir, { recursive: true, force: true });
});