"""
用户建模辩证更新层

职责:
- 冲突检测
- 内部推理讨论
- 模型升级决策
"""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ._db import get_db
from ._dialectic_conflict import detect_conflicts as _detect_conflicts
from ._dialectic_resolution import reason_about_conflicts as _reason_about_conflicts

if TYPE_CHECKING:
    from src.client import LLMGateway


class DialecticEngine:
    """辩证更新引擎"""

    def __init__(self, llm_gateway: "LLMGateway | None" = None):
        self._llm_gateway = llm_gateway

    def set_llm_gateway(self, gateway: "LLMGateway") -> None:
        """设置 LLM Gateway"""
        self._llm_gateway = gateway

    async def detect_conflicts(
        self, observations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """检测新证据与旧模型的矛盾"""
        return _detect_conflicts(observations)

    async def reason_about_conflicts(
        self, conflicts: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """内部推理讨论"""
        return await _reason_about_conflicts(self._llm_gateway, conflicts)

    def record_dialectical_history(
        self,
        conflicts: list[dict[str, Any]],
        resolution: dict[str, Any],
        updates: list[dict[str, Any]],
    ) -> None:
        """记录辩证进化历史"""
        timestamp = datetime.now(tz=UTC).isoformat()

        conflict_json = json.dumps(conflicts, ensure_ascii=False)
        resolution_json = json.dumps(resolution, ensure_ascii=False)
        update_json = json.dumps(updates, ensure_ascii=False)

        db = get_db()
        db._ensure_conn().execute(
            """
            INSERT INTO dialectical_history (conflict, resolution, update_record, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            (conflict_json, resolution_json, update_json, timestamp),
        )
        db._ensure_conn().commit()

    def get_dialectical_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取辩证进化历史"""
        db = get_db()
        rows = (
            db._ensure_conn()
            .execute(
                """
            SELECT id, conflict, resolution, update_record, timestamp, reasoning_log
            FROM dialectical_history
            ORDER BY timestamp DESC
            LIMIT ?
        """,
                (limit,),
            )
            .fetchall()
        )

        return [
            {
                "id": row["id"],
                "conflict": json.loads(row["conflict"]),
                "resolution": json.loads(row["resolution"]),
                "update": json.loads(row["update_record"]),
                "timestamp": row["timestamp"],
                "reasoning_log": row["reasoning_log"],
            }
            for row in rows
        ]


# 单例
_dialectic_engine: DialecticEngine | None = None


def get_dialectic_engine() -> DialecticEngine:
    """获取辩证引擎单例"""
    global _dialectic_engine
    if _dialectic_engine is None:
        _dialectic_engine = DialecticEngine()
    return _dialectic_engine