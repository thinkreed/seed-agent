"""
用户建模观察提取器

职责:
- 从用户交互中提取观察
- 提取偏好线索
- 提取行为模式
"""

import json
from typing import Any


class ObservationExtractor:
    """观察提取器 - 从用户交互中提取观察数据"""

    def extract_from_interaction(self, interaction: dict[str, Any]) -> list[dict[str, Any]]:
        """从用户交互中提取观察数据

        Args:
            interaction: {
                "user_message": str,
                "agent_response": str,
                "tool_calls": list,
                "feedback": str | None
            }

        Returns:
            观察数据列表，每项包含 evidence_type, data, context, confidence
        """
        observations = []

        user_message = interaction.get("user_message", "")
        feedback = interaction.get("feedback")

        # 提取偏好线索
        preferences = self._extract_preferences_from_message(user_message)
        for pref in preferences:
            observations.append({
                "evidence_type": "preference",
                "data": pref,
                "context": user_message[:200],
                "confidence": 0.7,
            })

        # 提取行为模式
        tool_calls = interaction.get("tool_calls", [])
        if tool_calls:
            behaviors = self._extract_behaviors_from_tools(tool_calls)
            for beh in behaviors:
                observations.append({
                    "evidence_type": "behavior",
                    "data": beh,
                    "context": json.dumps(tool_calls[:3], ensure_ascii=False),
                    "confidence": 0.6,
                })

        # 显式反馈
        if feedback:
            observations.append({
                "evidence_type": "feedback",
                "data": {"key": "explicit_feedback", "value": feedback},
                "context": user_message[:200],
                "confidence": 0.9,
            })

        return observations

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


# 单例
_extractor: ObservationExtractor | None = None


def get_observation_extractor() -> ObservationExtractor:
    """获取观察提取器单例"""
    global _extractor
    if _extractor is None:
        _extractor = ObservationExtractor()
    return _extractor