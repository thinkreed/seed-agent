"""
Session 上下文构建模块

处理从事件流构建 LLM 上下文的逻辑。
"""

from typing import Any

from src.session_stream._replay import StateReplay
from src.session_stream._summary import SummaryManager
from src.session_stream._types import EventType


class ContextBuilder:
    """LLM 上下文构建器"""

    def __init__(self):
        self._summary_manager = SummaryManager()
        self._replay = StateReplay()

    def build_context(
        self,
        events: list[dict[str, Any]],
        system_prompt: str | None = None,
        max_recent_events: int | None = None,
    ) -> list[dict[str, Any]]:
        """从事件流构建 LLM 上下文

        Args:
            events: 事件列表
            system_prompt: 系统提示
            max_recent_events: 最大最近事件数

        Returns:
            LLM 消息列表
        """
        messages: list[dict[str, Any]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        last_boundary = self._summary_manager.find_last_boundary_marker(events)

        if last_boundary:
            self._add_boundary_context(messages, last_boundary)

        context_event_types: list[str | EventType] = [
            EventType.USER_INPUT,
            EventType.LLM_RESPONSE,
            EventType.TOOL_RESULT,
            EventType.SYSTEM_MESSAGE,
        ]

        start_id = last_boundary["id"] + 1 if last_boundary else 0
        recent_events = [e for e in events if e["id"] >= start_id]

        # 过滤事件类型
        type_values = [t if isinstance(t, str) else t.value for t in context_event_types]
        recent_events = [e for e in recent_events if e["type"] in type_values]

        if max_recent_events and len(recent_events) > max_recent_events:
            recent_events = recent_events[-max_recent_events:]

        for event in recent_events:
            msg = self._replay.event_to_message(event)
            if msg:
                messages.append(msg)

        return messages

    def _add_boundary_context(
        self,
        messages: list[dict[str, Any]],
        boundary: dict[str, Any],
    ) -> None:
        """添加边界标记上下文"""
        event_type = boundary["type"]
        data = boundary["data"]

        if event_type == EventType.SUMMARY_MARKER.value:
            summary_content = data.get("summary", "")
            messages.append(
                {"role": "user", "content": f"[历史摘要]\n{summary_content}"}
            )
        elif event_type == EventType.CONTEXT_RESET.value:
            preserved = data.get("preserved_context")
            iteration = data.get("iteration", 0)
            if preserved:
                messages.append(
                    {
                        "role": "system",
                        "content": f"[迭代 {iteration} 状态摘要]\n{preserved}",
                    }
                )