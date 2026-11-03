/** SQLite 在线备份：VACUUM INTO 生成一致快照，供生产运维定时备份/迁移。 */
import type { SqliteStore } from "./store.ts";
export declare function backupStore(store: SqliteStore, target: string): void;
