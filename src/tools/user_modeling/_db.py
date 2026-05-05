"""
用户建模数据库层

职责:
- 数据库连接管理
- Schema 创建和维护
- 基础 CRUD 操作
"""

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_db_path() -> Path:
    """获取数据库路径（动态）"""
    try:
        from src.shared_config import get_paths_config
        return get_paths_config().memory_dir / "user_modeling.db"
    except RuntimeError:
        return Path.home() / ".seed" / "memory" / "user_modeling.db"


USER_MODELING_DB_PATH: Path | None = None


def _ensure_db_path() -> Path:
    """确保数据库路径已初始化"""
    global USER_MODELING_DB_PATH
    if USER_MODELING_DB_PATH is None:
        USER_MODELING_DB_PATH = _get_db_path()
    return USER_MODELING_DB_PATH


class UserModelingDB:
    """用户建模数据库管理器"""

    _instance: "UserModelingDB | None" = None
    _initialized: bool = False
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, db_path: str | Path | None = None) -> "UserModelingDB":
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path: str | Path | None = None):
        with UserModelingDB._lock:
            if UserModelingDB._initialized:
                return
            UserModelingDB._initialized = True

        self.db_path = str(db_path or _ensure_db_path())
        self.conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库连接和 Schema"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # 性能优化 PRAGMA
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute("PRAGMA busy_timeout=5000;")

        self._create_schema()

    def close(self) -> None:
        """关闭数据库连接"""
        if self.conn:
            try:
                self.conn.close()
            except sqlite3.Error as e:
                logger.warning(f"Database close error: {type(e).__name__}: {e}")
            finally:
                self.conn = None
                UserModelingDB._instance = None
                UserModelingDB._initialized = False

    def _ensure_conn(self) -> sqlite3.Connection:
        """确保数据库连接可用"""
        if self.conn is None:
            raise RuntimeError("Database connection is closed")
        return self.conn

    def _create_schema(self) -> None:
        """创建数据库 Schema"""
        cursor = self._ensure_conn().cursor()

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
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_profiles_key ON user_profiles(preference_key)"
        )

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
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_observations_type ON user_observations(observation_type)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_observations_time ON user_observations(timestamp)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_observations_unprocessed ON user_observations(processed)"
        )

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
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_dialectical_time ON dialectical_history(timestamp)"
        )

        self._ensure_conn().commit()

    # === 基础 CRUD 操作 ===

    def get_preference(self, key: str) -> dict[str, Any] | None:
        """从数据库获取偏好"""
        row = (
            self._ensure_conn()
            .execute(
                """
            SELECT preference_value, confidence, last_updated, metadata
            FROM user_profiles
            WHERE preference_key = ?
            ORDER BY last_updated DESC
            LIMIT 1
        """,
                (key,),
            )
            .fetchone()
        )

        if row:
            pref_data = json.loads(row["preference_value"])
            return {
                "value": pref_data.get("usual", pref_data.get("value")),
                "confidence": pref_data.get("confidence", row["confidence"]),
                "last_updated": pref_data.get("last_updated", row["last_updated"]),
                "exceptions": pref_data.get("exceptions", {}),
                "usual": pref_data.get("usual", pref_data.get("value")),
            }
        return None

    def get_preferences_batch(self, keys: set[str]) -> dict[str, dict[str, Any]]:
        """批量从数据库获取偏好"""
        if not keys:
            return {}

        placeholders = ",".join("?" * len(keys))
        rows = (
            self._ensure_conn()
            .execute(
                f"""
            SELECT preference_key, preference_value, confidence, last_updated, metadata
            FROM user_profiles
            WHERE preference_key IN ({placeholders})
            ORDER BY preference_key, last_updated DESC
        """,
                list(keys),
            )
            .fetchall()
        )

        result: dict[str, dict[str, Any]] = {}
        seen_keys: set[str] = set()

        for row in rows:
            key = row["preference_key"]
            if key in seen_keys:
                continue
            seen_keys.add(key)

            pref_data = json.loads(row["preference_value"])
            result[key] = {
                "value": pref_data.get("usual", pref_data.get("value")),
                "confidence": pref_data.get("confidence", row["confidence"]),
                "last_updated": pref_data.get("last_updated", row["last_updated"]),
                "exceptions": pref_data.get("exceptions", {}),
                "usual": pref_data.get("usual", pref_data.get("value")),
            }

        return result

    def save_preference(self, key: str, pref_data: dict[str, Any]) -> None:
        """保存偏好到数据库"""
        profile_id = f"user_{key}"
        value_json = json.dumps(pref_data, ensure_ascii=False)
        metadata = json.dumps(
            {"exceptions": pref_data.get("exceptions", {})}, ensure_ascii=False
        )

        self._ensure_conn().execute(
            """
            INSERT OR REPLACE INTO user_profiles
                (profile_id, preference_key, preference_value, confidence, last_updated, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                profile_id,
                key,
                value_json,
                pref_data["confidence"],
                pref_data["last_updated"],
                metadata,
            ),
        )
        self._ensure_conn().commit()

    def update_preference_confidence(self, key: str, new_confidence: float, timestamp: str) -> None:
        """更新偏好置信度"""
        self._ensure_conn().execute(
            """
            UPDATE user_profiles
            SET confidence = ?, last_updated = ?
            WHERE preference_key = ?
        """,
            (new_confidence, timestamp, key),
        )
        self._ensure_conn().commit()

    def delete_preference(self, key: str) -> None:
        """删除偏好"""
        self._ensure_conn().execute(
            "DELETE FROM user_profiles WHERE preference_key = ?", (key,)
        )
        self._ensure_conn().commit()

    def get_all_preferences(self) -> dict[str, dict[str, Any]]:
        """获取所有偏好"""
        rows = (
            self._ensure_conn()
            .execute("""
            SELECT preference_key, preference_value, confidence
            FROM user_profiles
        """)
            .fetchall()
        )

        preferences = {}
        for row in rows:
            preferences[row["preference_key"]] = json.loads(row["preference_value"])

        return preferences


# 单例访问函数
def get_db() -> UserModelingDB:
    """获取数据库单例"""
    return UserModelingDB()