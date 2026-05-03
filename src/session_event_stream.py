"""
Session 不可变事件流模块

基于 Harness Engineering "宠物与牲畜基础设施哲学" 设计：
- Session 是宠物：精心培育、持久保存、不可丢失
- 核心接口：emitEvent() 记录事件、getEvents() 读取事件
- 只追加的日志，天然支持重放和状态恢复
- 赋予智能体容错能力

特性：
- 只追加事件流，不可修改历史
- JSONL 持久化，支持崩溃恢复
- 摘要标记机制，不截断历史
- 重放能力，可恢复任意状态
"""

import json
import logging
import os
import time
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 默认存储路径
DEFAULT_STORAGE_PATH = Path(os.path.expanduser("~")) / ".seed" / "memory" / "events"


class EventType(str, Enum):
    """事件类型枚举"""

    # 对话事件
    USER_INPUT = "user_input"           # 用户输入
    LLM_RESPONSE = "llm_response"       # LLM 响应
    TOOL_CALL = "tool_call"             # 工具调用
    TOOL_RESULT = "tool_result"         # 工具结果

    # 上下文事件
    SUMMARY_GENERATED = "summary_generated"  # 摘要生成
    SUMMARY_MARKER = "summary_marker"        # 摘要标记 (不截断历史)
    CONTEXT_RESET = "context_reset"          # 上下文重置

    # 子代理事件
    SUBAGENT_SPAWN = "subagent_spawn"        # 子代理创建
    SUBAGENT_RESULT = "subagent_result"      # 子代理结果

    # 系统事件
    SESSION_START = "session_start"          # 会话开始
    SESSION_END = "session_end"              # 会话结束
    ERROR_OCCURRED = "error_occurred"        # 错误发生
    STATE_PERSISTED = "state_persisted"      # 状态持久化


class SessionEventStream:
    """不可变事件流 - 只追加日志

    核心设计原则：
    1. 只追加：历史不可修改、不可截断、不可清空
    2. 可重放：支持从任意事件 ID 重放状态
    3. 完整审计：所有操作有完整历史记录
    4. 摘要安全：摘要只创建标记，不丢失历史
    """

    def __init__(self, session_id: str, storage_path: Path | None = None):
        """初始化事件流

        Args:
            session_id: 会话唯一标识
            storage_path: 事件存储路径，默认 ~/.seed/memory/events
        """
        self.session_id = session_id
        self._storage_path = storage_path or DEFAULT_STORAGE_PATH
        self._events: list[dict[str, Any]] = []
        self._event_counter: int = 0
        self._loaded: bool = False

        # 确保存储目录存在
        os.makedirs(self._storage_path, exist_ok=True)

        # 加载已存在的事件
        self._load_existing_events()

    # === 核心接口 (只两个) ===

    def emit_event(self, event_type: str | EventType, event_data: dict[str, Any]) -> int:
        """记录事件 - 只追加，不可修改

        Args:
            event_type: 事件类型
            event_data: 事件数据

        Returns:
            int: 事件 ID (用于后续引用)
        """
        event_id = self._event_counter + 1
        event = {
            "id": event_id,
            "timestamp": time.time(),
            "type": event_type if isinstance(event_type, str) else event_type.value,
            "data": event_data,
            "session_id": self.session_id
        }

        # 内存追加
        self._events.append(event)
        self._event_counter = event_id

        # 持久化
        self._persist_event(event)

        logger.debug(f"Event emitted: id={event_id}, type={event['type']}")
        return event_id

    def get_events(
        self,
        start_id: int = 0,
        end_id: int | None = None,
        event_types: list[str | EventType] | None = None
    ) -> list[dict[str, Any]]:
        """读取事件 - 支持范围查询和类型过滤

        Args:
            start_id: 起始事件 ID (默认 0 = 全部，1 = 第一个事件)
            end_id: 结束事件 ID (默认 None = 到最新)
            event_types: 过滤的事件类型列表 (默认 None = 全部类型)

        Returns:
            事件列表
        """
        # 按事件 ID 过滤（事件 ID 从 1 开始）
        if start_id > 0:
            events = [e for e in self._events if e["id"] >= start_id]
        else:
            events = self._events.copy()

        if end_id is not None:
            events = [e for e in events if e["id"] <= end_id]

        # 类型过滤
        if event_types:
            type_values = [
                t if isinstance(t, str) else t.value
                for t in event_types
            ]
            events = [e for e in events if e["type"] in type_values]

        return events

    # === 恢复能力 ===

    def replay_to_state(self, target_event_id: int) -> dict[str, Any]:
        """重放事件到指定状态

        Args:
            target_event_id: 目标事件 ID (0 = 空状态，1 = 第一个事件后)

        Returns:
            dict: 重放后的状态摘要
        """
        state: dict[str, Any] = {
            "messages": [],
            "context": {},
            "last_summary": None,
            "conversation_rounds": 0
        }

        if target_event_id <= 0:
            return state

        # 重放所有事件直到目标 ID（按事件 ID 而不是索引）
        for event in self._events:
            if event["id"] <= target_event_id:
                state = self._apply_event_to_state(state, event)

        return state

    def get_state_at_event(self, event_id: int) -> dict[str, Any]:
        """获取指定事件点的状态快照"""
        return self.replay_to_state(event_id)

    def get_current_state(self) -> dict[str, Any]:
        """获取当前状态"""
        return self.replay_to_state(self._event_counter)

    def _apply_event_to_state(
        self,
        state: dict[str, Any],
        event: dict[str, Any]
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
            state["messages"].append({
                "role": "user",
                "content": data.get("content", "")
            })
            state["conversation_rounds"] += 1

        elif event_type == EventType.LLM_RESPONSE.value:
            msg: dict[str, Any] = {
                "role": "assistant",
                "content": data.get("content")
            }
            if data.get("tool_calls"):
                msg["tool_calls"] = data["tool_calls"]
            state["messages"].append(msg)

        elif event_type == EventType.TOOL_CALL.value:
            state["messages"].append({
                "role": "assistant",
                "tool_calls": [data]
            })

        elif event_type == EventType.TOOL_RESULT.value:
            state["messages"].append({
                "role": "tool",
                "tool_call_id": data.get("tool_call_id"),
                "content": data.get("content", "")
            })

        elif event_type == EventType.SUMMARY_MARKER.value:
            state["last_summary"] = {
                "event_id": event["id"],
                "summary": data.get("summary", ""),
                "covers_events": data.get("covers_events", [])
            }

        elif event_type == EventType.CONTEXT_RESET.value:
            state["messages"] = data.get("preserved_messages", [])
            state["context"] = data.get("preserved_context", {})

        elif event_type == EventType.ERROR_OCCURRED.value:
            state["context"]["last_error"] = data

        return state

    # === 摘要支持 (不修改原数据) ===

    def create_summary_marker(
        self,
        event_id: int,
        summary: str,
        metadata: dict[str, Any] | None = None
    ) -> int:
        """创建摘要标记 (不截断历史)

        Args:
            event_id: 摘要覆盖的事件范围终点
            summary: LLM 生成的摘要
            metadata: 可选元数据

        Returns:
            摘要事件 ID
        """
        marker_data: dict[str, Any] = {
            "covers_events": list(range(1, event_id + 1)),
            "summary": summary,
            "created_at": time.time()
        }

        if metadata:
            marker_data["metadata"] = metadata

        return self.emit_event(EventType.SUMMARY_MARKER, marker_data)

    def find_last_summary_marker(self) -> dict[str, Any] | None:
        """找到最近的摘要标记"""
        for event in reversed(self._events):
            if event["type"] == EventType.SUMMARY_MARKER.value:
                return event
        return None

    def get_events_since_last_summary(
        self,
        event_types: list[str | EventType] | None = None
    ) -> list[dict[str, Any]]:
        """获取最近摘要标记之后的事件

        Args:
            event_types: 过滤的事件类型列表

        Returns:
            事件列表
        """
        last_summary = self.find_last_summary_marker()

        if last_summary:
            start_id = last_summary["id"] + 1
        else:
            start_id = 0

        return self.get_events(start_id, event_types=event_types)

    # === 持久化 ===

    def _persist_event(self, event: dict[str, Any]) -> None:
        """持久化单个事件 (JSONL 格式)"""
        event_file = self._storage_path / f"{self.session_id}.jsonl"

        try:
            with open(event_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except IOError as e:
            logger.error(f"Failed to persist event: {type(e).__name__}: {e}")

    def _load_existing_events(self) -> None:
        """加载已存在的事件"""
        if self._loaded:
            return

        event_file = self._storage_path / f"{self.session_id}.jsonl"

        if not event_file.exists():
            self._loaded = True
            return

        try:
            with open(event_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                        self._events.append(event)
                        self._event_counter = max(
                            self._event_counter,
                            event.get("id", 0)
                        )
                    except json.JSONDecodeError as e:
                        logger.warning(
                            f"Failed to parse event: {type(e).__name__}: {str(e)[:50]}"
                        )
                        continue

            self._loaded = True
            logger.info(
                f"Loaded {len(self._events)} events for session {self.session_id}"
            )
        except IOError as e:
            logger.warning(f"Failed to load events: {type(e).__name__}: {e}")

    # === 辅助方法 ===

    def get_event_count(self) -> int:
        """获取事件总数"""
        return self._event_counter

    def get_last_event(self) -> dict[str, Any] | None:
        """获取最后一个事件"""
        if self._events:
            return self._events[-1]
        return None

    def get_event_by_id(self, event_id: int) -> dict[str, Any] | None:
        """根据 ID 获取事件"""
        for event in self._events:
            if event["id"] == event_id:
                return event
        return None

    def build_context_for_llm(
        self,
        system_prompt: str | None = None,
        max_recent_events: int | None = None
    ) -> list[dict[str, Any]]:
        """从事件流构建 LLM 上下文

        关键: 使用摘要标记而非截断历史

        Args:
            system_prompt: 系统提示
            max_recent_events: 最大最近事件数 (用于上下文窗口限制)

        Returns:
            messages 格式的上下文
        """
        messages: list[dict[str, Any]] = []

        # 1. 添加系统提示
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 2. 找到最近的摘要标记
        last_summary = self.find_last_summary_marker()

        # 3. 添加摘要作为上下文
        if last_summary:
            summary_content = last_summary["data"].get("summary", "")
            messages.append({
                "role": "user",
                "content": f"[历史摘要]\n{summary_content}"
            })

        # 4. 获取摘要点后的事件
        context_event_types: list[str | EventType] = [
            EventType.USER_INPUT,
            EventType.LLM_RESPONSE,
            EventType.TOOL_RESULT
        ]

        recent_events = self.get_events_since_last_summary(context_event_types)

        # 5. 应用上下文窗口限制
        if max_recent_events and len(recent_events) > max_recent_events:
            recent_events = recent_events[-max_recent_events:]

        # 6. 转换事件为消息
        for event in recent_events:
            msg = self._event_to_message(event)
            if msg:
                messages.append(msg)

        return messages

    def _event_to_message(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """将事件转换为消息格式"""
        event_type = event["type"]
        data = event["data"]

        if event_type == EventType.USER_INPUT.value:
            return {"role": "user", "content": data.get("content", "")}

        elif event_type == EventType.LLM_RESPONSE.value:
            msg: dict[str, Any] = {"role": "assistant"}
            content = data.get("content")
            if content:
                msg["content"] = content
            if data.get("tool_calls"):
                msg["tool_calls"] = data["tool_calls"]
            return msg

        elif event_type == EventType.TOOL_RESULT.value:
            return {
                "role": "tool",
                "tool_call_id": data.get("tool_call_id"),
                "content": data.get("content", "")
            }

        return None

    def record_session_start(self, metadata: dict[str, Any] | None = None) -> int:
        """记录会话开始"""
        return self.emit_event(
            EventType.SESSION_START,
            {"metadata": metadata or {}}
        )

    def record_session_end(self, reason: str = "normal") -> int:
        """记录会话结束"""
        return self.emit_event(
            EventType.SESSION_END,
            {"reason": reason, "event_count": self._event_counter}
        )

    def record_error(
        self,
        error_type: str,
        error_message: str,
        context: dict[str, Any] | None = None
    ) -> int:
        """记录错误"""
        return self.emit_event(
            EventType.ERROR_OCCURRED,
            {
                "error_type": error_type,
                "error_message": error_message,
                "context": context or {}
            }
        )