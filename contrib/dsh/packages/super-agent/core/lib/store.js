/** 存储：append-only 事件表 + outbox + cursors（node:sqlite）。唯一写入口是 append()。 */
import { createHash } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import { validateEvent } from "./events.js";
import { rebuild } from "./reducer.js";
import { apply } from "./reducer.js";
import { canonicalState } from "./store_hash.js";
const SCHEMA = `
CREATE TABLE IF NOT EXISTS events (
  seq  INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL,
  at   REAL NOT NULL,
  data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
  id         TEXT PRIMARY KEY,
  kind       TEXT NOT NULL,
  payload    TEXT NOT NULL,
  state      TEXT NOT NULL,
  attempts   INTEGER NOT NULL DEFAULT 0,
  next_at    REAL NOT NULL,
  created_at REAL NOT NULL,
  last_error TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS cursors (
  source     TEXT PRIMARY KEY,
  position   TEXT NOT NULL,
  updated_at REAL NOT NULL
);
`;
export class SqliteStore {
    db;
    cache = null;
    cacheSeq = -1;
    constructor(path = ":memory:") {
        this.db = new DatabaseSync(path);
        this.db.exec("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;" + SCHEMA);
    }
    append(event) {
        return this.appendAll([event])[0];
    }
    /** 批量追加：先用当前状态逐个试跑，非法事件在落库前就抛错，避免污染历史。 */
    appendAll(events) {
        if (events.length === 0)
            return [];
        let next = this.state();
        for (const event of events) {
            validateEvent(event);
            next = apply(next, event);
        }
        const statement = this.db.prepare("INSERT INTO events (type, at, data) VALUES (?, ?, ?)");
        const written = [];
        this.db.exec("BEGIN");
        try {
            for (const event of events) {
                const info = statement.run(event.type, event.at, JSON.stringify(event.data));
                written.push({ ...event, seq: Number(info.lastInsertRowid) });
            }
            this.db.exec("COMMIT");
        }
        catch (error) {
            this.db.exec("ROLLBACK");
            throw error;
        }
        this.cache = next;
        this.cacheSeq = this.lastSeq();
        return written;
    }
    events(after = 0) {
        const rows = this.db
            .prepare("SELECT seq, type, at, data FROM events WHERE seq > ? ORDER BY seq")
            .all(after);
        return rows.map((row) => ({ type: row.type, data: JSON.parse(row.data), at: row.at, seq: row.seq }));
    }
    lastSeq() {
        const row = this.db.prepare("SELECT COALESCE(MAX(seq), 0) AS seq FROM events").get();
        return Number(row.seq);
    }
    state() {
        const last = this.lastSeq();
        if (this.cache === null || this.cacheSeq !== last) {
            this.cache = rebuild(this.events());
            this.cacheSeq = last;
        }
        return this.cache;
    }
    replayHash() {
        return createHash("sha256").update(canonicalState(this.state())).digest("hex");
    }
    outboxEnqueue(id, kind, payload, at) {
        this.db
            .prepare("INSERT OR IGNORE INTO outbox (id, kind, payload, state, attempts, next_at, created_at)" +
            " VALUES (?, ?, ?, 'pending', 0, ?, ?)")
            .run(id, kind, JSON.stringify(payload), at, at);
    }
    outboxDue(now) {
        const rows = this.db
            .prepare("SELECT * FROM outbox WHERE state = 'pending' AND next_at <= ? ORDER BY created_at, id")
            .all(now);
        return rows.map(toItem);
    }
    outboxMark(id, state, attempts, nextAt, error = "") {
        this.db
            .prepare("UPDATE outbox SET state = ?, attempts = ?, next_at = ?, last_error = ? WHERE id = ?")
            .run(state, attempts, nextAt, error, id);
    }
    outboxGet(id) {
        const row = this.db.prepare("SELECT * FROM outbox WHERE id = ?").get(id);
        return row ? toItem(row) : null;
    }
    /** 是否还有未完成的 stored work（含尚未到退避时间的）。 */
    outboxHasPending() {
        const row = this.db.prepare("SELECT 1 AS found FROM outbox WHERE state = 'pending' LIMIT 1").get();
        return row !== undefined;
    }
    /** 已有 outbox ID（重启后给 ID 工厂预热，避免撞号）。 */
    outboxIds() {
        return this.db.prepare("SELECT id FROM outbox").all().map((row) => row.id);
    }
    cursorGet(source) {
        const row = this.db.prepare("SELECT position FROM cursors WHERE source = ?").get(source);
        return row ? row.position : null;
    }
    cursorSet(source, position, updatedAt) {
        this.db
            .prepare("INSERT INTO cursors (source, position, updated_at) VALUES (?, ?, ?)" +
            " ON CONFLICT(source) DO UPDATE SET position = excluded.position, updated_at = excluded.updated_at")
            .run(source, position, updatedAt);
    }
    backupDatabase(target) { this.db.prepare("VACUUM INTO ?").run(target); }
    close() {
        this.db.close();
    }
}
function toItem(row) {
    return {
        id: row.id,
        kind: row.kind,
        payload: JSON.parse(row.payload),
        state: row.state,
        attempts: row.attempts,
        nextAt: row.next_at,
        createdAt: row.created_at,
        lastError: row.last_error,
    };
}
//# sourceMappingURL=store.js.map