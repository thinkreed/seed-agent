"""
用户建模观察层

职责:
- 观察用户行为和偏好
- 从交互中提取观察
- 观察记录管理
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from ._db import get_db

logger = logging.getLogger(__name__)


class ObservationManager:
    """观察管理器"""

    def observe(
        self,
        evidence_type: str,
        data: dict[str, Any],
        context: str | None = None,
        confidence: float = 0.8,
    ) -> str:
        """观察新证据

        Args:
            evidence_type: "preference" | "behavior" | "feedback" | "context"
            data: 具体观察内容，格式 {"key": "...", "value": "..."}
            context: 观察上下文
            confidence: 置信度 (0.0-1.0)

        Returns:
            观察记录状态
        """
        if evidence_type not in ("preference", "behavior", "feedback", "context"):
            return f"Invalid evidence type: {evidence_type}"

        if not (0.0 <= confidence <= 1.0):
            return f"Invalid confidence: {confidence} (must be 0.0-1.0)"

        timestamp = datetime.now(tz=UTC).isoformat()
        data_json = json.dumps(data, ensure_ascii=False)
        db = get_db()

        try:
            db._ensure_conn().execute(
                """
                INSERT INTO user_observations
                    (observation_type, observation_data, context, confidence, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """,
                (evidence_type, data_json, context or "", confidence, timestamp),
            )
            db._ensure_conn().commit()

            return (
                f"Observation recorded: {evidence_type} -> {data.get('key', 'unknown')}"
            )
        except Exception as e:
            return f"Error recording observation: {type(e).__name__}: {e}"

    def observe_from_interaction(self, interaction: dict[str, Any]) -> list[str]:
        """从用户交互中提取观察

        Args:
            interaction: {
                "user_message": str,
                "agent_response": str,
                "tool_calls": list,
                "feedback": str | None
            }

        Returns:
            观察记录列表
        """
        results = []

        user_message = interaction.get("user_message", "")
        feedback = interaction.get("feedback")

        # 提取偏好线索
        preferences = self._extract_preferences_from_message(user_message)
        for pref in preferences:
            result = self.observe(
                evidence_type="preference",
                data=pref,
                context=user_message[:200],
                confidence=0.7,
            )
            results.append(result)

        # 提取行为模式
        tool_calls = interaction.get("tool_calls", [])
        if tool_calls:
            behaviors = self._extract_behaviors_from_tools(tool_calls)
            for beh in behaviors:
                result = self.observe(
                    evidence_type="behavior",
                    data=beh,
                    context=json.dumps(tool_calls[:3], ensure_ascii=False),
                    confidence=0.6,
                )
                results.append(result)

        # 显式反馈
        if feedback:
            result = self.observe(
                evidence_type="feedback",
                data={"key": "explicit_feedback", "value": feedback},
                context=user_message[:200],
                confidence=0.9,
            )
            results.append(result)

        return results

    def _extract_preferences_from_message(self, message: str) -> list[dict[str, Any]]:
        """从用户消息中提取偏好线索"""
        preferences = []

        # 正向偏好
        if "我喜欢" in message or "prefer" in message.lower():
            preferences.append(
                {"key": "general_style", "value": "user_likes", "raw": message[:100]}
            )

        # 格式偏好
        if "格式" in message or "format" in message.lower():
            preferences.append(
                {
                    "key": "output_format",
                    "value": "specified_format",
                    "raw": message[:100],
                }
            )

        # 语言偏好
        if "用中文" in message or "用英文" in message:
            lang = "中文" if "中文" in message else "英文"
            preferences.append({"key": "language", "value": lang, "raw": message[:100]})

        return preferences

    def _extract_behaviors_from_tools(
        self, tool_calls: list[dict]
    ) -> list[dict[str, Any]]:
        """从工具调用中提取行为模式"""
        behaviors = []

        for tc in tool_calls[:5]:
            tool_name = tc.get("function", {}).get("name", "unknown")
            behaviors.append(
                {"key": "tool_usage", "value": tool_name, "frequency": "observed"}
            )

        return behaviors

    def get_unprocessed_observations(self, limit: int = 50) -> list[dict[str, Any]]:
        """获取未处理的观察记录"""
        db = get_db()
        rows = (
            db._ensure_conn()
            .execute(
                """
            SELECT id, observation_type, observation_data, context, confidence, timestamp
            FROM user_observations
            WHERE processed = 0
            ORDER BY timestamp ASC
            LIMIT ?
        """,
                (limit,),
            )
            .fetchall()
        )

        observations = []
        for row in rows:
            data = json.loads(row["observation_data"])
            observations.append(
                {
                    "id": row["id"],
                    "type": row["observation_type"],
                    "data": data,
                    "context": row["context"],
                    "confidence": row["confidence"],
                    "timestamp": row["timestamp"],
                }
            )

        return observations

    def mark_observations_processed(self, observations: list[dict[str, Any]]) -> None:
        """标记观察已处理"""
        ids = [str(o["id"]) for o in observations]
        if ids:
            db = get_db()
            placeholders = ",".join("?" * len(ids))
            db._ensure_conn().execute(
                f"UPDATE user_observations SET processed = 1 WHERE id IN ({placeholders})",
                ids,
            )
            db._ensure_conn().commit()

    def clear_all_observations(self) -> str:
        """清除所有观察记录"""
        db = get_db()
        db._ensure_conn().execute("DELETE FROM user_observations")
        db._ensure_conn().commit()
        return "All observations cleared"


# 单例
_observation_manager: ObservationManager | None = None


def get_observation_manager() -> ObservationManager:
    """获取观察管理器单例"""
    global _observation_manager
    if _observation_manager is None:
        _observation_manager = ObservationManager()
    return _observation_manager