"""
用户建模升级底层操作

职责:
- 设置新偏好
- 添加例外情况
- 升级偏好值
"""

import logging
from datetime import UTC, datetime
from typing import Any

from ._db import get_db

logger = logging.getLogger(__name__)


def set_preference(key: str, value: str, confidence: float) -> None:
    """设置新偏好"""
    pref_data = {
        "usual": value,
        "exceptions": {},
        "confidence": confidence,
        "last_updated": datetime.now(tz=UTC).isoformat(),
    }
    db = get_db()
    db.save_preference(key, pref_data)


def add_exception(key: str, value: str, context: str, confidence: float) -> None:
    """添加例外情况"""
    db = get_db()
    existing = db.get_preference(key)
    if not existing:
        return

    exceptions = existing.get("exceptions", {})
    when_key = context[:50]
    exceptions[when_key] = {
        "value": value,
        "when": context,
        "confidence": confidence,
    }

    pref_data = {
        "usual": existing.get("usual", existing.get("value")),
        "exceptions": exceptions,
        "confidence": existing["confidence"],
        "last_updated": datetime.now(tz=UTC).isoformat(),
    }
    db.save_preference(key, pref_data)


def upgrade_preference(key: str, new_value: str, new_confidence: float) -> None:
    """升级偏好值"""
    db = get_db()
    existing = db.get_preference(key)
    if not existing:
        return

    exceptions = existing.get("exceptions", {})
    old_usual = existing.get("usual", existing.get("value"))
    exceptions["previously"] = {
        "value": old_usual,
        "when": "升级前的偏好值",
        "confidence": existing["confidence"],
    }

    pref_data = {
        "usual": new_value,
        "exceptions": exceptions,
        "confidence": new_confidence,
        "last_updated": datetime.now(tz=UTC).isoformat(),
    }
    db.save_preference(key, pref_data)