"""
用户建模检索层

职责:
- 偏好检索
- 用户画像摘要
- 历史查询
"""

import json
import logging
from typing import Any

from ._db import get_db
from ._dialectic import get_dialectic_engine

logger = logging.getLogger(__name__)


class RetrievalManager:
    """检索管理器"""

    def get_user_preference(
        self, key: str, context: str | None = None
    ) -> dict[str, Any]:
        """获取用户偏好"""
        db = get_db()
        existing = db.get_preference(key)

        if not existing:
            return {"value": None, "reason": "无此偏好记录", "confidence": 0.0}

        # 检查例外匹配
        exceptions = existing.get("exceptions", {})
        if context and exceptions:
            for exc_key, exc_value in exceptions.items():
                if exc_key in context or context in exc_key:
                    return {
                        "value": exc_value.get("value"),
                        "reason": f"例外情况: {exc_value.get('when', exc_key)}",
                        "confidence": exc_value.get("confidence", 0.7),
                    }

        return {
            "value": existing.get("usual", existing.get("value")),
            "reason": "常规偏好",
            "confidence": existing.get("confidence", 0.5),
        }

    def get_user_profile_summary(self) -> str:
        """获取用户画像摘要"""
        db = get_db()
        rows = (
            db._ensure_conn()
            .execute("""
            SELECT preference_key, preference_value, confidence
            FROM user_profiles
            ORDER BY confidence DESC, last_updated DESC
        """)
            .fetchall()
        )

        if not rows:
            return "无用户画像数据"

        lines = ["用户画像摘要:"]
        for row in rows:
            pref_data = json.loads(row["preference_value"])
            usual = pref_data.get("usual", "未知")
            exceptions = pref_data.get("exceptions", {})

            if exceptions:
                exception_strs = [
                    f"{k}: {v.get('value', '未知')}"
                    for k, v in exceptions.items()
                    if k != "previously"
                ]
                if exception_strs:
                    lines.append(
                        f"- {row['preference_key']}: 平时 {usual}, "
                        f"例外情况 {', '.join(exception_strs[:3])}"
                    )
                else:
                    lines.append(f"- {row['preference_key']}: {usual}")
            else:
                lines.append(f"- {row['preference_key']}: {usual}")

        return chr(10).join(lines)

    def get_all_preferences(self) -> dict[str, dict[str, Any]]:
        """获取所有偏好"""
        db = get_db()
        return db.get_all_preferences()

    def get_dialectical_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取辩证进化历史"""
        engine = get_dialectic_engine()
        return engine.get_dialectical_history(limit)

    def clear_preference(self, key: str) -> str:
        """清除特定偏好"""
        db = get_db()
        db.delete_preference(key)
        return f"Preference cleared: {key}"


# 单例
_retrieval_manager: RetrievalManager | None = None


def get_retrieval_manager() -> RetrievalManager:
    """获取检索管理器单例"""
    global _retrieval_manager
    if _retrieval_manager is None:
        _retrieval_manager = RetrievalManager()
    return _retrieval_manager