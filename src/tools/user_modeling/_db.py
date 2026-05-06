"""用户建模数据库层

拆分架构:
- _db_init.py: 单例模式和连接管理
- _db_schema.py: Schema 创建
- _db_crud.py: CRUD 操作
"""

import sqlite3
from pathlib import Path
from typing import Any

from ._db_crud import (
    delete_preference,
    get_all_preferences,
    get_preference,
    get_preferences_batch,
    save_preference,
    update_preference_confidence,
)
from ._db_init import DBConnectionManager, get_connection_manager
from ._db_schema import create_schema


class UserModelingDB:
    """用户建模数据库管理器（向后兼容包装）"""

    def __init__(self, db_path: str | Path | None = None):
        self._manager = get_connection_manager(db_path)
        self.conn = self._manager.conn
        create_schema(self._ensure_conn())

    def close(self) -> None:
        self._manager.close()
        self.conn = None

    def _ensure_conn(self) -> sqlite3.Connection:
        return self._manager.ensure_conn()

    # CRUD 方法委托
    def get_preference(self, key: str) -> dict[str, Any] | None:
        return get_preference(self._ensure_conn(), key)

    def get_preferences_batch(self, keys: set[str]) -> dict[str, dict[str, Any]]:
        return get_preferences_batch(self._ensure_conn(), keys)

    def save_preference(self, key: str, pref_data: dict[str, Any]) -> None:
        save_preference(self._ensure_conn(), key, pref_data)

    def update_preference_confidence(self, key: str, new_confidence: float, timestamp: str) -> None:
        update_preference_confidence(self._ensure_conn(), key, new_confidence, timestamp)

    def delete_preference(self, key: str) -> None:
        delete_preference(self._ensure_conn(), key)

    def get_all_preferences(self) -> dict[str, dict[str, Any]]:
        return get_all_preferences(self._ensure_conn())


def get_db(db_path: str | Path | None = None) -> UserModelingDB:
    """获取数据库单例"""
    return UserModelingDB(db_path)


__all__ = ["UserModelingDB", "get_db"]