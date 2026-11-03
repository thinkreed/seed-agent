/** 单 Runtime 租约：同一个事件库同时只允许一个 Engine 进程写状态。 */

import { closeSync, existsSync, openSync, readFileSync, unlinkSync, writeFileSync } from "node:fs";

export interface RuntimeLock {
  release(): void;
}

interface LockPayload {
  readonly pid: number;
}

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

export function acquireRuntimeLock(dbPath: string): RuntimeLock {
  if (dbPath === ":memory:") return { release: () => undefined };
  const path = `${dbPath}.lock`;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const fd = openSync(path, "wx");
      const payload: LockPayload = { pid: process.pid };
      writeFileSync(fd, JSON.stringify(payload), "utf8");
      closeSync(fd);
      return {
        release: () => {
          try {
            const current = JSON.parse(readFileSync(path, "utf8")) as Partial<LockPayload>;
            if (current.pid === process.pid) unlinkSync(path);
          } catch {
            // lock already gone or unreadable
          }
        },
      };
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (code !== "EEXIST") throw error;
      let owner: Partial<LockPayload> = {};
      try {
        owner = JSON.parse(readFileSync(path, "utf8")) as Partial<LockPayload>;
      } catch {
        // corrupt lock; treat as stale below
      }
      if (typeof owner.pid === "number" && alive(owner.pid)) {
        throw new Error(`runtime already active on ${dbPath} (pid ${owner.pid})`);
      }
      try {
        unlinkSync(path);
      } catch {
        // another process may have removed it
      }
    }
  }
  throw new Error(`cannot acquire runtime lock: ${path}`);
}

export function runtimeLockHeld(dbPath: string): boolean {
  if (dbPath === ":memory:" || !existsSync(`${dbPath}.lock`)) return false;
  try {
    const owner = JSON.parse(readFileSync(`${dbPath}.lock`, "utf8")) as Partial<LockPayload>;
    return typeof owner.pid === "number" && alive(owner.pid);
  } catch {
    return false;
  }
}