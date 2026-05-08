"""
Session 摘要支持 API

提供摘要标记相关的便捷方法，封装对 SummaryManager 的调用。
"""

from typing import Any

from src.session_stream._types import EventType
from src.session_stream._summary import SummaryManager


class SummaryAPI:
    """摘要 API 门面类"""

    def __init__(self, summary_manager: SummaryManager):
        self._manager = summary_manager

    def create_summary_marker(
        self,
        emit_event_func,
        event_id: int,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """创建摘要标记

        Args:
            emit_event_func: 事件发射函数
            event_id: 关联的事件 ID
            summary: 摘要内容
            metadata: 元数据

        Returns:
            事件 ID
        """
        marker_data = self._manager.create_summary_marker_data(
            event_id, summary, metadata
        )
        return emit_event_func(EventType.SUMMARY_MARKER, marker_data)

    def create_context_reset_marker(
        self,
        emit_event_func,
        iteration: int,
        preserved_context: str | None = None,
    ) -> int:
        """创建上下文重置标记

        Args:
            emit_event_func: 事件发射函数
            iteration: 迭代次数
            preserved_context: 保留的上下文

        Returns:
            事件 ID
        """
        marker_data = self._manager.create_context_reset_data(
            iteration, preserved_context
        )
        return emit_event_func(EventType.CONTEXT_RESET, marker_data)

    def find_last_summary_marker(
        self, events: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """找到最近的摘要标记"""
        return self._manager.find_last_summary_marker(events)

    def find_last_reset_marker(
        self, events: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """找到最近的上下文重置标记"""
        return self._manager.find_last_reset_marker(events)

    def find_last_boundary_marker(
        self, events: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """找到最近的边界标记"""
        return self._manager.find_last_boundary_marker(events)

    def get_events_since_last_summary(
        self,
        events: list[dict[str, Any]],
        event_types: list[str | EventType] | None = None,
    ) -> list[dict[str, Any]]:
        """获取最近摘要标记之后的事件"""
        last_summary = self.find_last_summary_marker(events)
        result = self._manager.get_events_since_marker(events, last_summary)
        if event_types:
            type_values = [t if isinstance(t, str) else t.value for t in event_types]
            result = [e for e in result if e["type"] in type_values]
        return result