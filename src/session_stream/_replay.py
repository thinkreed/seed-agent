"""
Session 事件重放模块

处理状态重放和事件应用逻辑。
"""

import logging
from typing import Any

from src.session_stream._types import EventType

logger = logging.getLogger(__name__)


class StateReplay:
    """状态重放管理器"""

    def replay_to_state(
        self,
        events: list[dict[str, Any]],
        target_event_id: int,
    ) -> dict[str, Any]:
        """重放事件到指定状态

        Args:
            events: 事件列表
            target_event_id: 目标事件 ID

        Returns:
            重放后的状态摘要
        """
        state: dict[str, Any] = {
            "messages": [],
            "context": {},
            "last_summary": None,
            "conversation_rounds": 0,
        }

        if target_event_id <= 0:
            return state

        # 重放所有事件直到目标 ID
        for event in events:
            if event["id"] <= target_event_id:
                state = self._apply_event_to_state(state, event)

        return state

    def _apply_event_to_state(
        self,
        state: dict[str, Any],
        event: dict[str, Any],
    ) -> dict[str, Any]:
        """应用单个事件到状态

        Args:
            state: 当前状态
            event: 待应用的事件

        Returns:
            更新后的状态
        """
        event_type = event["type"]
        data = event["data"]

        if event_type == EventType.USER_INPUT.value:
            state["messages"].append(
                {"role": "user", "content": data.get("content", "")}
            )
            state["conversation_rounds"] += 1

        elif event_type == EventType.LLM_RESPONSE.value:
            msg: dict[str, Any] = {"role": "assistant", "content": data.get("content")}
            if data.get("tool_calls"):
                msg["tool_calls"] = data["tool_calls"]
            state["messages"].append(msg)

        elif event_type == EventType.TOOL_CALL.value:
            state["messages"].append({"role": "assistant", "tool_calls": [data]})

        elif event_type == EventType.TOOL_RESULT.value:
            state["messages"].append(
                {
                    "role": "tool",
                    "tool_call_id": data.get("tool_call_id"),
                    "content": data.get("content", ""),
                }
            )

        elif event_type == EventType.SUMMARY_MARKER.value:
            state["last_summary"] = {
                "event_id": event["id"],
                "summary": data.get("summary", ""),
                "covers_events": data.get("covers_events", []),
            }

        elif event_type == EventType.CONTEXT_RESET.value:
            state["messages"] = data.get("preserved_messages", [])
            state["context"] = data.get("preserved_context", {})

        elif event_type == EventType.ERROR_OCCURRED.value:
            state["context"]["last_error"] = data

        return state

    def event_to_message(
        self,
        event: dict[str, Any],
    ) -> dict[str, Any] | None:
        """将事件转换为消息格式"""
        event_type = event["type"]
        data = event["data"]

        if event_type == EventType.USER_INPUT.value:
            return {"role": "user", "content": data.get("content", "")}

        if event_type == EventType.LLM_RESPONSE.value:
            msg: dict[str, Any] = {"role": "assistant"}
            content = data.get("content")
            if content:
                msg["content"] = content
            if data.get("tool_calls"):
                msg["tool_calls"] = data["tool_calls"]
            return msg

        if event_type == EventType.TOOL_RESULT.value:
            return {
                "role": "tool",
                "tool_call_id": data.get("tool_call_id"),
                "content": data.get("content", ""),
            }

        if event_type == EventType.SYSTEM_MESSAGE.value:
            content = data.get("content", "")
            if content:
                return {"role": "user", "content": content}

        return None