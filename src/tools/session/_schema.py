"""
Schema 创建方法模块

包含数据库 Schema 的创建方法：
- _create_schema, _create_session_messages_schema, _create_sessions_meta_schema
- _create_gene_outcomes_schema, _create_gene_outcomes_triggers, _create_gene_outcomes_indexes
"""

import sqlite3


def create_session_messages_schema(conn: sqlite3.Connection) -> None:
    """创建 session_messages 表和索引"""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            tool_calls_json TEXT,
            tool_call_id TEXT,
            message_type TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    for idx in ["session_id", "timestamp", "role"]:
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS idx_session_messages_{idx} ON session_messages({idx})"
        )
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS session_messages_fts
        USING fts5(content, session_id, role,
            tokenize='unicode61 remove_diacritics 2', prefix='2 3 4')
    """)


def create_sessions_meta_schema(conn: sqlite3.Connection) -> None:
    """创建 sessions_meta 表和索引"""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions_meta (
            session_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            last_updated TEXT,
            message_count INTEGER DEFAULT 0,
            summary TEXT
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_meta_created ON sessions_meta(created_at)"
    )


def create_gene_outcomes_schema(conn: sqlite3.Connection) -> None:
    """创建 gene_outcomes 表和 FTS5 虚拟表"""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gene_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name TEXT NOT NULL,
            signal_pattern TEXT NOT NULL,
            outcome_status TEXT NOT NULL,
            outcome_score REAL NOT NULL,
            session_id TEXT,
            timestamp TEXT NOT NULL,
            iteration_context TEXT,
            intent TEXT,
            blast_radius TEXT,
            CONSTRAINT unique_outcome UNIQUE (skill_name, signal_pattern, timestamp)
        )
    """)
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS gene_outcomes_fts USING fts5(
            signal_pattern, skill_name, outcome_status,
            content='gene_outcomes', content_rowid='id',
            tokenize='unicode61 remove_diacritics 2')
    """)


def create_gene_outcomes_triggers(conn: sqlite3.Connection) -> None:
    """创建 gene_outcomes FTS5 同步触发器"""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS gene_outcomes_ai AFTER INSERT ON gene_outcomes BEGIN
            INSERT INTO gene_outcomes_fts(rowid, signal_pattern, skill_name, outcome_status)
            VALUES (new.id, new.signal_pattern, new.skill_name, new.outcome_status);
        END
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS gene_outcomes_ad AFTER DELETE ON gene_outcomes BEGIN
            INSERT INTO gene_outcomes_fts(gene_outcomes_fts, rowid, signal_pattern, skill_name, outcome_status)
            VALUES ('delete', old.id, old.signal_pattern, old.skill_name, old.outcome_status);
        END
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS gene_outcomes_au AFTER UPDATE ON gene_outcomes BEGIN
            INSERT INTO gene_outcomes_fts(gene_outcomes_fts, rowid, signal_pattern, skill_name, outcome_status)
            VALUES ('delete', old.id, old.signal_pattern, old.skill_name, old.outcome_status);
            INSERT INTO gene_outcomes_fts(rowid, signal_pattern, skill_name, outcome_status)
            VALUES (new.id, new.signal_pattern, new.skill_name, new.outcome_status);
        END
    """)


def create_gene_outcomes_indexes(conn: sqlite3.Connection) -> None:
    """创建 gene_outcomes 索引"""
    cursor = conn.cursor()
    for col in ["skill_name", "timestamp", "outcome_status", "session_id"]:
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS idx_gene_{col} ON gene_outcomes({col})"
        )

    # 复合索引：优化近期统计查询 (skill_name + timestamp)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_gene_skill_time ON gene_outcomes(skill_name, timestamp)"
    )


def create_schema(conn: sqlite3.Connection) -> None:
    """创建数据库 Schema（主入口）"""
    create_session_messages_schema(conn)
    create_sessions_meta_schema(conn)
    create_gene_outcomes_schema(conn)
    create_gene_outcomes_triggers(conn)
    create_gene_outcomes_indexes(conn)
    conn.commit()


__all__ = [
    "create_gene_outcomes_indexes",
    "create_gene_outcomes_schema",
    "create_gene_outcomes_triggers",
    "create_schema",
    "create_session_messages_schema",
    "create_sessions_meta_schema",
]
