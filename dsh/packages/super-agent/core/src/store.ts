/** 存储：append-only 事件表 + outbox + cursors（node:sqlite）。唯一写入口是 append()。 */

import { createHash } from "node:crypto";
import { DatabaseSync } from "node:sqlite";

import type { State } from "./domain.ts";
import type { AnyEvent } from "./events.ts";
import { validateEvent } from "./events.ts";
import { rebuild } from "./reducer.ts";
import { apply } from "./reducer.ts";
import { canonicalState } from "./store_hash.ts";

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

export interface OutboxItem {
  readonly id: string;
  readonly kind: string;
  readonly payload: Record<string, unknown>;
  readonly state: string;
  readonly attempts: number;
  readonly nextAt: number;
  readonly createdAt: number;
  readonly lastError: string;
}

interface EventRow {
  seq: number;
  type: string;
  at: number;
  data: string;
}

interface OutboxRow {
  id: string;
  kind: string;
  payload: string;
  state: string;
  attempts: number;
  next_at: number;
  created_at: number;
  last_error: string;
}

export class SqliteStore {
  private readonly db: DatabaseSync;
  private cache: State | null = null;
  private cacheSeq = -1;

  constructor(path = ":memory:") {
    this.db = new DatabaseSync(path);
    this.db.exec(SCHEMA);
  }

  append(event: AnyEvent): AnyEvent {
    return this.appendAll([event])[0] as AnyEvent;
  }

  /** 批量追加：先用当前状态逐个试跑，非法事件在落库前就抛错，避免污染历史。 */
  appendAll(events: readonly AnyEvent[]): AnyEvent[] {
    if (events.length === 0) return [];
    let next = this.state();
    for (const event of events) {
      validateEvent(event);
      next = apply(next, event);
    }
    const statement = this.db.prepare("INSERT INTO events (type, at, data) VALUES (?, ?, ?)");
    const written: AnyEvent[] = [];
    this.db.exec("BEGIN");
    try {
      for (const event of events) {
        const info = statement.run(event.type, event.at, JSON.stringify(event.data));
        written.push({ ...event, seq: Number(info.lastInsertRowid) } as AnyEvent);
      }
      this.db.exec("COMMIT");
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    }
    this.cache = next;
    this.cacheSeq = this.lastSeq();
    return written;
  }

  events(after = 0): AnyEvent[] {
    const rows = this.db
      .prepare("SELECT seq, type, at, data FROM events WHERE seq > ? ORDER BY seq")
      .all(after) as unknown as EventRow[];
    return rows.map(
      (row) => ({ type: row.type, data: JSON.parse(row.data), at: row.at, seq: row.seq }) as AnyEvent,
    );
  }

  lastSeq(): number {
    const row = this.db.prepare("SELECT COALESCE(MAX(seq), 0) AS seq FROM events").get() as {
      seq: number;
    };
    return Number(row.seq);
  }

  state(): State {
    const last = this.lastSeq();
    if (this.cache === null || this.cacheSeq !== last) {
      this.cache = rebuild(this.events());
      this.cacheSeq = last;
    }
    return this.cache;
  }

  replayHash(): string {
    return createHash("sha256").update(canonicalState(this.state())).digest("hex");
  }

  outboxEnqueue(id: string, kind: string, payload: Record<string, unknown>, at: number): void {
    this.db
      .prepare(
        "INSERT OR IGNORE INTO outbox (id, kind, payload, state, attempts, next_at, created_at)" +
          " VALUES (?, ?, ?, 'pending', 0, ?, ?)",
      )
      .run(id, kind, JSON.stringify(payload), at, at);
  }

  outboxDue(now: number): OutboxItem[] {
    const rows = this.db
      .prepare("SELECT * FROM outbox WHERE state = 'pending' AND next_at <= ? ORDER BY created_at, id")
      .all(now) as unknown as OutboxRow[];
    return rows.map(toItem);
  }

  outboxMark(id: string, state: string, attempts: number, nextAt: number, error = ""): void {
    this.db
      .prepare("UPDATE outbox SET state = ?, attempts = ?, next_at = ?, last_error = ? WHERE id = ?")
      .run(state, attempts, nextAt, error, id);
  }

  outboxGet(id: string): OutboxItem | null {
    const row = this.db.prepare("SELECT * FROM outbox WHERE id = ?").get(id) as
      | OutboxRow
      | undefined;
    return row ? toItem(row) : null;
  }

  /** 是否还有未完成的 stored work（含尚未到退避时间的）。 */
  outboxHasPending(): boolean {
    const row = this.db.prepare("SELECT 1 AS found FROM outbox WHERE state = 'pending' LIMIT 1").get();
    return row !== undefined;
  }

  /** 已有 outbox ID（重启后给 ID 工厂预热，避免撞号）。 */
  outboxIds(): string[] {
    return (this.db.prepare("SELECT id FROM outbox").all() as { id: string }[]).map((row) => row.id);
  }

  cursorGet(source: string): string | null {
    const row = this.db.prepare("SELECT position FROM cursors WHERE source = ?").get(source) as
      | { position: string }
      | undefined;
    return row ? row.position : null;
  }

  cursorSet(source: string, position: string, updatedAt: number): void {
    this.db
      .prepare(
        "INSERT INTO cursors (source, position, updated_at) VALUES (?, ?, ?)" +
          " ON CONFLICT(source) DO UPDATE SET position = excluded.position, updated_at = excluded.updated_at",
      )
      .run(source, position, updatedAt);
  }

  close(): void {
    this.db.close();
  }
}

function toItem(row: OutboxRow): OutboxItem {
  return {
    id: row.id,
    kind: row.kind,
    payload: JSON.parse(row.payload) as Record<string, unknown>,
    state: row.state,
    attempts: row.attempts,
    nextAt: row.next_at,
    createdAt: row.created_at,
    lastError: row.last_error,
  };
}
