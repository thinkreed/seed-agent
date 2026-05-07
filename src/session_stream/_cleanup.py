"""
Session 事件清理模块

处理旧事件的清理和自动清理逻辑。
"""

import logging
import time
from typing import Any

from src.session_stream._types import (
    MAX_EVENT_AGE_DAYS,
    MAX_IN_MEMORY_EVENTS,
    EventType,
)

logger = logging.getLogger(__name__)


class EventCleanup:
    """事件清理管理器"""

    def auto_cleanup(
        self,
        events: list[dict[str, Any]],
        event_counter: int,
    ) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]], int]:
        """自动清理旧事件

        Args:
            events: 当前事件列表
            event_counter: 当前事件计数器

        Returns:
            (清理后的事件列表, 新索引, 清理数量)
        """
        if len(events) <= MAX_IN_MEMORY_EVENTS:
            return events, {e["id"]: e for e in events}, 0

        summary_marker_ids = self._find_summary_markers(events)
        cutoff_time = time.time() - (MAX_EVENT_AGE_DAYS * 24 * 3600)
        target_count = int(MAX_IN_MEMORY_EVENTS * 0.8)

        new_events = []
        for e in events:
            keep = (
                e["id"] in summary_marker_ids
                or e.get("timestamp", 0) >= cutoff_time
                or e["id"] > event_counter - target_count
            )
            if keep:
                new_events.append(e)

        new_index = {e["id"]: e for e in new_events}
        cleaned_count = len(events) - len(new_events)

        if cleaned_count > 0:
            logger.info(f"Auto-cleaned {cleaned_count} events")

        return new_events, new_index, cleaned_count

    def manual_cleanup(
        self,
        events: list[dict[str, Any]],
        event_counter: int,
        max_age_days: int | None = None,
        max_count: int | None = None,
        keep_summary_markers: bool = True,
    ) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]], int]:
        """手动清理旧事件

        Args:
            events: 当前事件列表
            event_counter: 当前事件计数器
            max_age_days: 最大保留天数
            max_count: 最大保留数量
            keep_summary_markers: 是否保留摘要标记

        Returns:
            (清理后的事件列表, 新索引, 清理数量)
        """
        max_age_days = max_age_days or MAX_EVENT_AGE_DAYS
        max_count = max_count or MAX_IN_MEMORY_EVENTS

        if len(events) <= max_count:
            return events, {e["id"]: e for e in events}, 0

        cutoff_time = time.time() - (max_age_days * 24 * 3600)
        summary_marker_ids = (
            self._find_summary_markers(events) if keep_summary_markers else set()
        )

        new_events = []
        for e in events:
            keep = (
                e["id"] in summary_marker_ids
                or e.get("timestamp", 0) >= cutoff_time
                or e["id"] > event_counter - max_count // 2
            )
            if keep:
                new_events.append(e)

        new_index = {e["id"]: e for e in new_events}
        cleaned_count = len(events) - len(new_events)

        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old events")

        return new_events, new_index, cleaned_count

    def _find_summary_markers(self, events: list[dict[str, Any]]) -> set[int]:
        """找出所有摘要标记的 ID"""
        marker_ids = set()
        for e in events:
            if e.get("type") == EventType.SUMMARY_MARKER.value:
                marker_ids.add(e["id"])
        return marker_ids