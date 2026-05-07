"""
Session 不可变事件流模块

基于 Harness Engineering "宠物与牲畜基础设施哲学" 设计：
- Session 是宠物：精心培育、持久保存、不可丢失
- 核心接口：emitEvent() 记录事件、getEvents() 读取事件
- 只追加的日志，天然支持重放和状态恢复
- 赋予智能体容错能力

重构说明：
- 类型定义移至 session_stream/_types.py
- 持久化逻辑移至 session_stream/_persist.py
- 重放逻辑移至 session_stream/_replay.py
- 清理逻辑移至 session_stream/_cleanup.py
- 摘要逻辑移至 session_stream/_summary.py
- 上下文构建移至 session_stream/_context.py
"""

import logging
import time
from pathlib import Path
from typing import Any

from src.session_stream import (
    ContextBuilder,
    EventCleanup,
    EventPersistence,
    EventType,
    StateReplay,
    SummaryManager,
    _get_default_storage_path,
)

logger = logging.getLogger(__name__)


class SessionEventStream:
    """不可变事件流 - 只追加日志

    核心设计原则：
    1. 只追加：历史不可修改、不可截断、不可清空
    2. 可重放：支持从任意事件 ID 重放状态
    3. 完整审计：所有操作有完整历史记录
    4. 摘要安全：摘要只创建标记，不丢失历史
    """

    def __init__(self, session_id: str, storage_path: Path | None = None):
        self.session_id = session_id
        self._storage_path = storage_path or _get_default_storage_path()
        self._events: list[dict[str, Any]] = []
        self._event_index: dict[int, dict[str, Any]] = {}
        self._event_counter: int = 0
        self._loaded: bool = False

        # 使用拆分模块的组件
        self._persistence = EventPersistence(self._storage_path)
        self._replay = StateReplay()
        self._cleanup = EventCleanup()
        self._summary_manager = SummaryManager()
        self._context_builder = ContextBuilder()

        self._persistence.ensure_dir_exists()
        self._load_existing_events()

    # === 核心接口 ===

    def emit_event(
        self, event_type: str | EventType, event_data: dict[str, Any]
    ) -> int:
        """记录事件 - 只追加，不可修改"""
        event_id = self._event_counter + 1
        event = {
            "id": event_id,
            "timestamp": time.time(),
            "type": event_type if isinstance(event_type, str) else event_type.value,
            "data": event_data,
            "session_id": self.session_id,
        }

        self._events.append(event)
        self._event_index[event_id] = event
        self._event_counter = event_id

        self._persistence.persist_event(self.session_id, event)
        logger.debug(f"Event emitted: id={event_id}, type={event['type']}")
        return event_id

    def get_events(
        self,
        start_id: int = 0,
        end_id: int | None = None,
        event_types: list[str | EventType] | None = None,
    ) -> list[dict[str, Any]]:
        """读取事件 - 支持范围查询和类型过滤"""
        type_values = None
        if event_types:
            type_values = [t if isinstance(t, str) else t.value for t in event_types]

        return [
            e
            for e in self._events
            if (start_id <= 0 or e["id"] >= start_id)
            and (end_id is None or e["id"] <= end_id)
            and (type_values is None or e["type"] in type_values)
        ]

    # === 清理 ===

    def cleanup_old_events(
        self,
        max_age_days: int | None = None,
        max_count: int | None = None,
        keep_summary_markers: bool = True,
    ) -> int:
        """清理旧事件"""
        new_events, new_index, cleaned = self._cleanup.manual_cleanup(
            self._events,
            self._event_counter,
            max_age_days,
            max_count,
            keep_summary_markers,
        )
        self._events = new_events
        self._event_index = new_index
        return cleaned

    # === 恢复能力 ===

    def replay_to_state(self, target_event_id: int) -> dict[str, Any]:
        """重放事件到指定状态"""
        return self._replay.replay_to_state(self._events, target_event_id)

    def get_state_at_event(self, event_id: int) -> dict[str, Any]:
        """获取指定事件点的状态快照"""
        return self.replay_to_state(event_id)

    def get_current_state(self) -> dict[str, Any]:
        """获取当前状态"""
        return self.replay_to_state(self._event_counter)

    # === 摘要支持 ===

    def create_summary_marker(
        self, event_id: int, summary: str, metadata: dict[str, Any] | None = None
    ) -> int:
        """创建摘要标记"""
        marker_data = self._summary_manager.create_summary_marker_data(
            event_id, summary, metadata
        )
        return self.emit_event(EventType.SUMMARY_MARKER, marker_data)

    def create_context_reset_marker(
        self, iteration: int, preserved_context: str | None = None
    ) -> int:
        """创建上下文重置标记"""
        marker_data = self._summary_manager.create_context_reset_data(
            iteration, preserved_context
        )
        return self.emit_event(EventType.CONTEXT_RESET, marker_data)

    def find_last_summary_marker(self) -> dict[str, Any] | None:
        """找到最近的摘要标记"""
        return self._summary_manager.find_last_summary_marker(self._events)

    def find_last_reset_marker(self) -> dict[str, Any] | None:
        """找到最近的上下文重置标记"""
        return self._summary_manager.find_last_reset_marker(self._events)

    def find_last_boundary_marker(self) -> dict[str, Any] | None:
        """找到最近的边界标记"""
        return self._summary_manager.find_last_boundary_marker(self._events)

    def get_events_since_last_summary(
        self, event_types: list[str | EventType] | None = None
    ) -> list[dict[str, Any]]:
        """获取最近摘要标记之后的事件"""
        last_summary = self.find_last_summary_marker()
        events = self._summary_manager.get_events_since_marker(
            self._events, last_summary
        )
        if event_types:
            type_values = [t if isinstance(t, str) else t.value for t in event_types]
            events = [e for e in events if e["type"] in type_values]
        return events

    # === LLM 上下文 ===

    def build_context_for_llm(
        self, system_prompt: str | None = None, max_recent_events: int | None = None
    ) -> list[dict[str, Any]]:
        """从事件流构建 LLM 上下文"""
        return self._context_builder.build_context(
            self._events, system_prompt, max_recent_events
        )

    # === 持久化 ===

    def _load_existing_events(self) -> None:
        """加载已存在的事件"""
        if self._loaded:
            return

        events = self._persistence.load_events(self.session_id)
        for event in events:
            self._events.append(event)
            event_id = event.get("id", 0)
            if event_id:
                self._event_index[event_id] = event
            self._event_counter = max(self._event_counter, event_id)

        self._loaded = True

    # === 辅助方法 ===

    def get_event_count(self) -> int:
        """获取事件总数"""
        return self._event_counter

    def get_last_event(self) -> dict[str, Any] | None:
        """获取最后一个事件"""
        return self._events[-1] if self._events else None

    def get_event_by_id(self, event_id: int) -> dict[str, Any] | None:
        """根据 ID 获取事件"""
        return self._event_index.get(event_id)

    def record_session_start(self, metadata: dict[str, Any] | None = None) -> int:
        """记录会话开始"""
        return self.emit_event(EventType.SESSION_START, {"metadata": metadata or {}})

    def record_session_end(self, reason: str = "normal") -> int:
        """记录会话结束"""
        return self.emit_event(
            EventType.SESSION_END,
            {"reason": reason, "event_count": self._event_counter},
        )

    def record_error(
        self, error_type: str, error_message: str, context: dict[str, Any] | None = None
    ) -> int:
        """记录错误"""
        return self.emit_event(
            EventType.ERROR_OCCURRED,
            {
                "error_type": error_type,
                "error_message": error_message,
                "context": context or {},
            },
        )


# 导出类型（向后兼容）
__all__ = ["EventType", "SessionEventStream"]