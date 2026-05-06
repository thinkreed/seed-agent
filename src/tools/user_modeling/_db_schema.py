"""用户建模数据库 Schema

职责:
- Schema 创建和维护
"""

import sqlite3


def create_schema(conn: sqlite3.Connection) -> None:
    """创建数据库 Schema"""
    cursor = conn.cursor()

    # 用户画像主表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            profile_id TEXT PRIMARY KEY,
            preference_key TEXT NOT NULL,
            preference_value TEXT NOT NULL,
            confidence REAL DEFAULT 0.8,
            last_updated TEXT NOT NULL,
            metadata TEXT,
            UNIQUE(profile_id, preference_key)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_profiles_key ON user_profiles(preference_key)")

    # 观察记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observation_type TEXT NOT NULL,
            observation_data TEXT NOT NULL,
            context TEXT,
            confidence REAL DEFAULT 0.8,
            timestamp TEXT NOT NULL,
            processed INTEGER DEFAULT 0
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_observations_type ON user_observations(observation_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_observations_time ON user_observations(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_observations_unprocessed ON user_observations(processed)")

    # 辩证进化历史表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dialectical_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conflict TEXT NOT NULL,
            resolution TEXT NOT NULL,
            update_record TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            reasoning_log TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dialectical_time ON dialectical_history(timestamp)")

    conn.commit()


__all__ = ["create_schema"]