/** SQLite 在线备份：VACUUM INTO 生成一致快照，供生产运维定时备份/迁移。 */

import { existsSync, mkdirSync, unlinkSync } from "node:fs";
import { dirname } from "node:path";

import type { SqliteStore } from "./store.ts";

export function backupStore(store: SqliteStore, target: string): void {
  mkdirSync(dirname(target), { recursive: true });
  if (existsSync(target)) unlinkSync(target);
  store.backupDatabase(target);
}