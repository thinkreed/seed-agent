/**
 * SQLite 在线备份：VACUUM INTO 生成一致快照。
 *
 *   node scripts/backup-super-agent.mjs <seed.db> <backup.db>
 */

import { SqliteStore } from "../src/store.ts";
import { backupStore } from "../src/store_backup.ts";

const [source, target] = process.argv.slice(2);
if (!source || !target) {
  console.error("usage: node scripts/backup-super-agent.mjs <seed.db> <backup.db>");
  process.exit(2);
}

const store = new SqliteStore(source);
try {
  backupStore(store, target);
  console.log(JSON.stringify({ ok: true, source, target, events: store.lastSeq() }));
} finally {
  store.close();
}