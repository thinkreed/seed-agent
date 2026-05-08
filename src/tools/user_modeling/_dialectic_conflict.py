"""
用户建模辩证更新层 - 冲突检测

职责:
- 检测新证据与旧模型的矛盾
- 冲突判断辅助函数
"""

from typing import Any

from ._db import get_db


def detect_conflicts(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """检测新证据与旧模型的矛盾"""
    conflicts = []

    # 收集偏好键
    pref_keys = set()
    for obs in observations:
        if obs["type"] == "preference":
            key = obs["data"].get("key")
            if key:
                pref_keys.add(key)

    # 批量获取偏好
    db = get_db()
    existing_prefs = db.get_preferences_batch(pref_keys) if pref_keys else {}

    for obs in observations:
        if obs["type"] != "preference":
            continue

        pref_key = obs["data"].get("key")
        pref_value = obs["data"].get("value")

        if not pref_key or not pref_value:
            continue

        existing = existing_prefs.get(pref_key)

        if existing and _is_conflicting(existing, pref_value, obs["context"]):
            conflicts.append(
                {
                    "preference_key": pref_key,
                    "old_belief": existing,
                    "new_evidence": pref_value,
                    "confidence_old": existing.get("confidence", 0.8),
                    "confidence_new": obs["confidence"],
                    "context": obs["context"],
                    "observation_id": obs["id"],
                }
            )

    return conflicts


def _is_conflicting(
    existing: dict[str, Any], new_value: str, context: str | None
) -> bool:
    """检查是否矛盾"""
    usual = existing.get("usual", existing.get("value"))

    if new_value == usual:
        return False

    # 检查例外情况
    exceptions = existing.get("exceptions", {})
    if context:
        for exc_key, exc_value in exceptions.items():
            if (
                exc_key in context or context in exc_key
            ) and new_value == exc_value.get("value"):
                return False

    return True