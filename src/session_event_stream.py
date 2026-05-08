"""Session 不可变事件流模块 - 只追加日志，支持重放和状态恢复"""

import logging
import time
from pathlib import Path
from typing import Any

from src.session_stream import (
    ContextBuilder, EventCleanup, EventPersistence, EventType, StateReplay,
    SummaryAPI, SummaryManager, _get_default_storage_path,
    record_error, record_session_end, record_session_start,
)

logger = logging.getLogger(__name__)


class SessionEventStream:
    """不可变事件流 - 只追加、可重放、完整审计"""

    def __init__(self, session_id: str, storage_path: Path | None = None):
        self.session_id = session_id
        self._storage_path = storage_path or _get_default_storage_path()
        self._events: list[dict[str, Any]] = []
        self._event_index: dict[int, dict[str, Any]] = {}
        self._event_counter: int = 0
        self._loaded: bool = False
        self._persistence = EventPersistence(self._storage_path)
        self._replay = StateReplay()
        self._cleanup = EventCleanup()
        self._summary_api = SummaryAPI(SummaryManager())
        self._context_builder = ContextBuilder()
        self._persistence.ensure_dir_exists()
        self._load_existing_events()

    def emit_event(self, event_type: str | EventType, event_data: dict[str, Any]) -> int:
        """记录事件 - 只追加"""
        event_id = self._event_counter + 1
        event = {
            "id": event_id, "timestamp": time.time(),
            "type": event_type if isinstance(event_type, str) else event_type.value,
            "data": event_data, "session_id": self.session_id,
        }
        self._events.append(event)
        self._event_index[event_id] = event
        self._event_counter = event_id
        self._persistence.persist_event(self.session_id, event)
        logger.debug(f"Event emitted: id={event_id}, type={event['type']}")
        return event_id

    def get_events(
        self, start_id: int = 0, end_id: int | None = None,
        event_types: list[str | EventType] | None = None,
    ) -> list[dict[str, Any]]:
        """读取事件"""
        type_values = [t if isinstance(t, str) else t.value for t in event_types] if event_types else None
        return [e for e in self._events
                if (start_id <= 0 or e["id"] >= start_id)
                and (end_id is None or e["id"] <= end_id)
                and (type_values is None or e["type"] in type_values)]

    def cleanup_old_events(
        self, max_age_days: int | None = None, max_count: int | None = None,
        keep_summary_markers: bool = True,
    ) -> int:
        """清理旧事件"""
        new_events, new_index, cleaned = self._cleanup.manual_cleanup(
            self._events, self._event_counter, max_age_days, max_count, keep_summary_markers)
        self._events = new_events
        self._event_index = new_index
        return cleaned

    def replay_to_state(self, target_event_id: int) -> dict[str, Any]:
        """重放事件到指定状态"""
        return self._replay.replay_to_state(self._events, target_event_id)

    def get_state_at_event(self, event_id: int) -> dict[str, Any]:
        return self.replay_to_state(event_id)

    def get_current_state(self) -> dict[str, Any]:
        return self.replay_to_state(self._event_counter)

    def create_summary_marker(
        self, event_id: int, summary: str, metadata: dict[str, Any] | None = None) -> int:
        return self._summary_api.create_summary_marker(self.emit_event, event_id, summary, metadata)

    def create_context_reset_marker(
        self, iteration: int, preserved_context: str | None = None) -> int:
        return self._summary_api.create_context_reset_marker(self.emit_event, iteration, preserved_context)

    def find_last_summary_marker(self) -> dict[str, Any] | None:
        return self._summary_api.find_last_summary_marker(self._events)

    def find_last_reset_marker(self) -> dict[str, Any] | None:
        return self._summary_api.find_last_reset_marker(self._events)

    def find_last_boundary_marker(self) -> dict[str, Any] | None:
        return self._summary_api.find_last_boundary_marker(self._events)

    def get_events_since_last_summary(
        self, event_types: list[str | EventType] | None = None) -> list[dict[str, Any]]:
        return self._summary_api.get_events_since_last_summary(self._events, event_types)

    def build_context_for_llm(
        self, system_prompt: str | None = None, max_recent_events: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._context_builder.build_context(self._events, system_prompt, max_recent_events)

    def _load_existing_events(self) -> None:
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

    def get_event_count(self) -> int:
        return self._event_counter

    def get_last_event(self) -> dict[str, Any] | None:
        return self._events[-1] if self._events else None

    def get_event_by_id(self, event_id: int) -> dict[str, Any] | None:
        return self._event_index.get(event_id)

    def record_session_start(self, metadata: dict[str, Any] | None = None) -> int:
        return record_session_start(self.emit_event, metadata)

    def record_session_end(self, reason: str = "normal") -> int:
        return record_session_end(self.emit_event, self._event_counter, reason)

    def record_error(
        self, error_type: str, error_message: str, context: dict[str, Any] | None = None) -> int:
        return record_error(self.emit_event, error_type, error_message, context)


__all__ = ["EventType", "SessionEventStream"]