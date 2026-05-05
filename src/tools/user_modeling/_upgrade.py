"""
用户建模升级层

职责:
- 模型强化（无矛盾时）
- 例外升级
- 值升级
- 偏好管理
"""

import logging
from datetime import UTC, datetime
from typing import Any

from ._db import get_db

logger = logging.getLogger(__name__)


class ModelUpgradeEngine:
    """模型升级引擎"""

    async def reinforce_model(self, observations: list[dict[str, Any]]) -> None:
        """强化现有模型（无矛盾时）"""
        for obs in observations:
            if obs["type"] != "preference":
                continue

            pref_key = obs["data"].get("key")
            pref_value = obs["data"].get("value")

            if not pref_key or not pref_value:
                continue

            db = get_db()
            existing = db.get_preference(pref_key)

            if existing:
                usual = existing.get("usual", existing.get("value"))

                if pref_value == usual:
                    # 相同值：强化置信度
                    new_confidence = min(1.0, existing["confidence"] + 0.05)
                    timestamp = datetime.now(tz=UTC).isoformat()
                    db.update_preference_confidence(pref_key, new_confidence, timestamp)
                elif obs.get("context"):
                    # 不同值但有上下文：添加例外
                    self._add_exception(pref_key, pref_value, obs["context"], obs["confidence"])
                elif obs["confidence"] > existing["confidence"]:
                    # 不同值无上下文：偏好升级
                    self._upgrade_preference(pref_key, pref_value, obs["confidence"])
            else:
                # 新偏好，直接设置
                self._set_preference(pref_key, pref_value, obs["confidence"])

    def upgrade_model(self, resolution: dict[str, Any]) -> list[dict[str, Any]]:
        """升级模型而非简单覆盖"""
        updates = []

        for res in resolution.get("resolutions", []):
            pref_key = res.get("preference_key")
            if not pref_key:
                continue

            db = get_db()
            existing = db.get_preference(pref_key)

            if res.get("resolution_type") == "exception":
                upgraded = self._apply_exception_upgrade(existing, res)
            else:
                upgraded = self._apply_value_upgrade(existing, res)

            db.save_preference(pref_key, upgraded)

            updates.append(
                {
                    "preference_key": pref_key,
                    "before": existing,
                    "after": upgraded,
                    "reason": res.get("reason", ""),
                }
            )

        return updates

    def _apply_exception_upgrade(
        self, existing: dict[str, Any] | None, resolution: dict[str, Any]
    ) -> dict[str, Any]:
        """添加例外升级"""
        if not existing:
            return {
                "usual": resolution["value"],
                "exceptions": {},
                "confidence": resolution["confidence"],
                "last_updated": datetime.now(tz=UTC).isoformat(),
            }

        exceptions = existing.get("exceptions", {})
        when_key = resolution.get("when", "general")[:50]
        exceptions[when_key] = {
            "value": resolution["value"],
            "when": resolution.get("when", ""),
            "confidence": resolution["confidence"],
        }

        return {
            "usual": existing.get("usual", existing.get("value")),
            "exceptions": exceptions,
            "confidence": min(existing["confidence"], resolution["confidence"]),
            "last_updated": datetime.now(tz=UTC).isoformat(),
        }

    def _apply_value_upgrade(
        self, existing: dict[str, Any] | None, resolution: dict[str, Any]
    ) -> dict[str, Any]:
        """升级常规偏好"""
        if not existing:
            return {
                "usual": resolution["value"],
                "exceptions": {},
                "confidence": resolution["confidence"],
                "last_updated": datetime.now(tz=UTC).isoformat(),
            }

        exceptions = existing.get("exceptions", {})
        old_usual = existing.get("usual", existing.get("value"))
        exceptions["previously"] = {
            "value": old_usual,
            "when": "之前的偏好",
            "confidence": existing["confidence"],
        }

        return {
            "usual": resolution["value"],
            "exceptions": exceptions,
            "confidence": resolution["confidence"],
            "last_updated": datetime.now(tz=UTC).isoformat(),
        }

    def _set_preference(self, key: str, value: str, confidence: float) -> None:
        """设置新偏好"""
        pref_data = {
            "usual": value,
            "exceptions": {},
            "confidence": confidence,
            "last_updated": datetime.now(tz=UTC).isoformat(),
        }
        db = get_db()
        db.save_preference(key, pref_data)

    def _add_exception(
        self, key: str, value: str, context: str, confidence: float
    ) -> None:
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

    def _upgrade_preference(
        self, key: str, new_value: str, new_confidence: float
    ) -> None:
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


# 单例
_upgrade_engine: ModelUpgradeEngine | None = None


def get_upgrade_engine() -> ModelUpgradeEngine:
    """获取升级引擎单例"""
    global _upgrade_engine
    if _upgrade_engine is None:
        _upgrade_engine = ModelUpgradeEngine()
    return _upgrade_engine