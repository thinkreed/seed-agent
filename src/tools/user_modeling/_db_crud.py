"""用户建模数据库 CRUD 操作"""

import json
import sqlite3
from typing import Any


def get_preference(conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
    """从数据库获取偏好"""
    row = conn.execute("""
        SELECT preference_value, confidence, last_updated, metadata
        FROM user_profiles
        WHERE preference_key = ?
        ORDER BY last_updated DESC
        LIMIT 1
    """, (key,)).fetchone()

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


def get_preferences_batch(conn: sqlite3.Connection, keys: set[str]) -> dict[str, dict[str, Any]]:
    """批量获取偏好"""
    if not keys:
        return {}

    placeholders = ",".join("?" * len(keys))
    rows = conn.execute(f"""
        SELECT preference_key, preference_value, confidence, last_updated, metadata
        FROM user_profiles
        WHERE preference_key IN ({placeholders})
        ORDER BY preference_key, last_updated DESC
    """, list(keys)).fetchall()

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


def save_preference(conn: sqlite3.Connection, key: str, pref_data: dict[str, Any]) -> None:
    """保存偏好"""
    profile_id = f"user_{key}"
    value_json = json.dumps(pref_data, ensure_ascii=False)
    metadata = json.dumps({"exceptions": pref_data.get("exceptions", {})}, ensure_ascii=False)

    conn.execute("""
        INSERT OR REPLACE INTO user_profiles
            (profile_id, preference_key, preference_value, confidence, last_updated, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (profile_id, key, value_json, pref_data["confidence"], pref_data["last_updated"], metadata))
    conn.commit()


def update_preference_confidence(conn: sqlite3.Connection, key: str, new_confidence: float, timestamp: str) -> None:
    """更新偏好置信度"""
    conn.execute("""
        UPDATE user_profiles
        SET confidence = ?, last_updated = ?
        WHERE preference_key = ?
    """, (new_confidence, timestamp, key))
    conn.commit()


def delete_preference(conn: sqlite3.Connection, key: str) -> None:
    """删除偏好"""
    conn.execute("DELETE FROM user_profiles WHERE preference_key = ?", (key,))
    conn.commit()


def get_all_preferences(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """获取所有偏好"""
    rows = conn.execute("""
        SELECT preference_key, preference_value, confidence
        FROM user_profiles
    """).fetchall()

    return {row["preference_key"]: json.loads(row["preference_value"]) for row in rows}


__all__ = [
    "get_preference",
    "get_preferences_batch",
    "save_preference",
    "update_preference_confidence",
    "delete_preference",
    "get_all_preferences",
]