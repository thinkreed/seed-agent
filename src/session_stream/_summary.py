"""
Session 事件摘要模块

处理摘要标记和边界标记的查找逻辑。
"""

import time
from typing import Any

from src.session_stream._types import EventType


class SummaryManager:
    """摘要标记管理器"""

    def create_summary_marker_data(
        self,
        event_id: int,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """创建摘要标记数据

        Args:
            event_id: 事件 ID
            summary: 摘要内容
            metadata: 元数据

        Returns:
            标记数据字典
        """
        marker_data: dict[str, Any] = {
            "covers_events": list(range(1, event_id + 1)),
            "summary": summary,
            "created_at": time.time(),
        }
        if metadata:
            marker_data["metadata"] = metadata
        return marker_data

    def create_context_reset_data(
        self,
        iteration: int,
        preserved_context: str | None = None,
    ) -> dict[str, Any]:
        """创建上下文重置标记数据

        Args:
            iteration: 迭代次数
            preserved_context: 保留的上下文

        Returns:
            标记数据字典
        """
        return {
            "iteration": iteration,
            "preserved_context": preserved_context,
            "created_at": time.time(),
        }

    def find_last_summary_marker(
        self,
        events: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """找到最近的摘要标记"""
        for event in reversed(events):
            if event["type"] == EventType.SUMMARY_MARKER.value:
                return event
        return None

    def find_last_reset_marker(
        self,
        events: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """找到最近的上下文重置标记"""
        for event in reversed(events):
            if event["type"] == EventType.CONTEXT_RESET.value:
                return event
        return None

    def find_last_boundary_marker(
        self,
        events: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """找到最近的边界标记"""
        for event in reversed(events):
            if event["type"] in (
                EventType.SUMMARY_MARKER.value,
                EventType.CONTEXT_RESET.value,
            ):
                return event
        return None

    def get_events_since_marker(
        self,
        events: list[dict[str, Any]],
        marker: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """获取标记之后的事件"""
        start_id = marker["id"] + 1 if marker else 0
        return [e for e in events if e["id"] >= start_id]