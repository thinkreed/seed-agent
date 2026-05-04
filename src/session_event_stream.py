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
import time
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 默认存储路径
DEFAULT_STORAGE_PATH = Path.home() / ".seed" / "memory" / "events"

# 事件清理配置
MAX_IN_MEMORY_EVENTS = 10000  # 内存中最大事件数
MAX_EVENT_AGE_DAYS = 30  # 事件最大保留天数


class EventType(str, Enum):
    """事件类型枚举"""

    # 对话事件
    USER_INPUT = "user_input"  # 用户输入
    LLM_RESPONSE = "llm_response"  # LLM 响应
    TOOL_CALL = "tool_call"  # 工具调用
    TOOL_RESULT = "tool_result"  # 工具结果

    # 上下文事件
    SUMMARY_GENERATED = "summary_generated"  # 摘要生成
    SUMMARY_MARKER = "summary_marker"  # 摘要标记 (不截断历史)
    CONTEXT_RESET = "context_reset"  # 上下文重置

    # 子代理事件
    SUBAGENT_SPAWN = "subagent_spawn"  # 子代理创建
    SUBAGENT_RESULT = "subagent_result"  # 子代理结果

    # 系统事件
    SESSION_START = "session_start"  # 会话开始
    SESSION_END = "session_end"  # 会话结束
    ERROR_OCCURRED = "error_occurred"  # 错误发生
    STATE_PERSISTED = "state_persisted"  # 状态持久化

    # 用户交互事件 (Ask User 机制)
    USER_QUESTION = "user_question"  # 发起问题
    USER_WAITING = "user_waiting"  # 等待用户响应
    USER_RESPONSE = "user_response"  # 用户响应
    USER_CANCELLED = "user_cancelled"  # 用户取消

    # 执行控制事件 (取消机制)
    EXECUTION_CANCEL = "execution_cancel"  # 执行取消
    EXECUTION_PAUSE = "execution_pause"  # 执行暂停
    EXECUTION_RESUME = "execution_resume"  # 执行恢复

    # 后台任务事件
    TASK_START = "task_start"  # 后台任务开始
    TASK_END = "task_end"  # 后台任务结束
    TASK_CANCEL = "task_cancel"  # 后台任务取消


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
        self._event_index: dict[int, dict[str, Any]] = {}  # 事件 ID -> 事件的索引
        self._event_counter: int = 0
        self._loaded: bool = False

        # 确保存储目录存在
        os.makedirs(self._storage_path, exist_ok=True)

        # 加载已存在的事件
        self._load_existing_events()

    # === 核心接口 (只两个) ===

    def emit_event(
        self, event_type: str | EventType, event_data: dict[str, Any]
    ) -> int:
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
            "session_id": self.session_id,
        }

        # 内存追加
        self._events.append(event)
        self._event_index[event_id] = event  # 维护索引
        self._event_counter = event_id

        # 自动清理：防止内存无限增长
        if len(self._events) > MAX_IN_MEMORY_EVENTS:
            self._auto_cleanup_events()

        # 持久化
        self._persist_event(event)

        logger.debug(f"Event emitted: id={event_id}, type={event['type']}")
        return event_id

    def get_events(
        self,
        start_id: int = 0,
        end_id: int | None = None,
        event_types: list[str | EventType] | None = None,
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
            type_values = [t if isinstance(t, str) else t.value for t in event_types]
            events = [e for e in events if e["type"] in type_values]

        return events

    def _auto_cleanup_events(self) -> int:
        """自动清理旧事件（内部方法，emit_event 调用）

        当事件数量超过 MAX_IN_MEMORY_EVENTS 时自动触发：
        - 保留所有摘要标记事件
        - 保留最近 80% 的事件
        - 清理超过 MAX_EVENT_AGE_DAYS 的旧事件

        Returns:
            int: 清理的事件数量
        """
        # 保留摘要标记事件
        summary_marker_ids = set()
        for e in self._events:
            if e.get("type") == EventType.SUMMARY_MARKER.value:
                summary_marker_ids.add(e["id"])

        cutoff_time = time.time() - (MAX_EVENT_AGE_DAYS * 24 * 3600)
        original_count = len(self._events)
        target_count = int(MAX_IN_MEMORY_EVENTS * 0.8)  # 目标保留 80%

        # 过滤：保留摘要标记 + 最近事件 + 未过期事件
        new_events = []
        for e in self._events:
            keep = (
                e["id"] in summary_marker_ids
                or e.get("timestamp", 0) >= cutoff_time
                or e["id"] > self._event_counter - target_count
            )
            if keep:
                new_events.append(e)

        # 更新索引
        self._events = new_events
        self._event_index = {e["id"]: e for e in new_events}
        cleaned_count = original_count - len(self._events)

        if cleaned_count > 0:
            logger.info(
                f"Auto-cleaned {cleaned_count} events for session {self.session_id}"
            )

        return cleaned_count

    def cleanup_old_events(
        self,
        max_age_days: int | None = None,
        max_count: int | None = None,
        keep_summary_markers: bool = True,
    ) -> int:
        """清理旧事件，防止内存无限增长

        Args:
            max_age_days: 最大保留天数，默认使用 MAX_EVENT_AGE_DAYS
            max_count: 最大保留数量，默认使用 MAX_IN_MEMORY_EVENTS
            keep_summary_markers: 是否保留摘要标记事件

        Returns:
            int: 清理的事件数量
        """
        max_age_days = max_age_days or MAX_EVENT_AGE_DAYS
        max_count = max_count or MAX_IN_MEMORY_EVENTS

        if len(self._events) <= max_count:
            return 0

        cutoff_time = time.time() - (max_age_days * 24 * 3600)
        original_count = len(self._events)

        # 保留摘要标记和最近事件
        summary_marker_ids = set()
        if keep_summary_markers:
            for e in self._events:
                if e.get("type") == EventType.SUMMARY_MARKER.value:
                    summary_marker_ids.add(e["id"])

        # 过滤：保留摘要标记 + 最近事件 + 未过期事件
        new_events = []
        for e in self._events:
            keep = (
                e["id"] in summary_marker_ids
                or e.get("timestamp", 0) >= cutoff_time
                or e["id"] > self._event_counter - max_count // 2  # 保留最近一半
            )
            if keep:
                new_events.append(e)

        self._events = new_events
        cleaned_count = original_count - len(self._events)

        if cleaned_count > 0:
            logger.info(
                f"Cleaned up {cleaned_count} old events for session {self.session_id}"
            )

        return cleaned_count

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
            "conversation_rounds": 0,
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
        self, state: dict[str, Any], event: dict[str, Any]
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

    # === 摘要支持 (不修改原数据) ===

    def create_summary_marker(
        self, event_id: int, summary: str, metadata: dict[str, Any] | None = None
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
            "created_at": time.time(),
        }

        if metadata:
            marker_data["metadata"] = metadata

        return self.emit_event(EventType.SUMMARY_MARKER, marker_data)

    def create_context_reset_marker(
        self, iteration: int, preserved_context: str | None = None
    ) -> int:
        """创建上下文重置标记 (Ralph Loop 使用)

        此标记用于指示上下文重置点，build_context_for_llm 会识别此标记
        并只返回重置点之后的事件。

        Args:
            iteration: 当前迭代次数
            preserved_context: 保留的关键上下文

        Returns:
            重置标记事件 ID
        """
        marker_data: dict[str, Any] = {
            "iteration": iteration,
            "preserved_context": preserved_context,
            "created_at": time.time(),
        }

        return self.emit_event(EventType.CONTEXT_RESET, marker_data)

    def find_last_summary_marker(self) -> dict[str, Any] | None:
        """找到最近的摘要标记"""
        for event in reversed(self._events):
            if event["type"] == EventType.SUMMARY_MARKER.value:
                return event
        return None

    def find_last_reset_marker(self) -> dict[str, Any] | None:
        """找到最近的上下文重置标记"""
        for event in reversed(self._events):
            if event["type"] == EventType.CONTEXT_RESET.value:
                return event
        return None

    def find_last_boundary_marker(self) -> dict[str, Any] | None:
        """找到最近的边界标记（摘要或上下文重置）

        用于确定构建上下文时的起始点。

        Returns:
            最近的边界标记事件，或 None
        """
        for event in reversed(self._events):
            if event["type"] in (
                EventType.SUMMARY_MARKER.value,
                EventType.CONTEXT_RESET.value,
            ):
                return event
        return None

    def get_events_since_last_summary(
        self, event_types: list[str | EventType] | None = None
    ) -> list[dict[str, Any]]:
        """获取最近摘要标记之后的事件

        Args:
            event_types: 过滤的事件类型列表

        Returns:
            事件列表
        """
        last_summary = self.find_last_summary_marker()

        start_id = last_summary["id"] + 1 if last_summary else 0

        return self.get_events(start_id, event_types=event_types)

    # === 持久化 ===

    def _persist_event(self, event: dict[str, Any], max_retries: int = 3) -> None:
        """持久化单个事件 (JSONL 格式)，带重试机制

        Args:
            event: 事件数据
            max_retries: 最大重试次数（默认3次）

        Raises:
            OSError: 重试失败后抛出异常，让调用方决定处理策略
        """
        event_file = self._storage_path / f"{self.session_id}.jsonl"

        last_error: OSError | None = None
        for attempt in range(max_retries):
            try:
                with open(event_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
                return  # 成功写入，直接返回
            except OSError as e:
                last_error = e
                logger.warning(
                    f"Failed to persist event (attempt {attempt + 1}/{max_retries}): "
                    f"{type(e).__name__}: {e}"
                )
                if attempt < max_retries - 1:
                    # 等待后重试（指数退避）
                    time.sleep(0.1 * (attempt + 1))

        # 所有重试失败后抛出异常
        if last_error:
            logger.error(
                f"Failed to persist event after {max_retries} retries: "
                f"{type(last_error).__name__}: {last_error}"
            )
            raise last_error

    def _load_existing_events(self) -> None:
        """加载已存在的事件"""
        if self._loaded:
            return

        event_file = self._storage_path / f"{self.session_id}.jsonl"

        if not event_file.exists():
            self._loaded = True
            return

        try:
            with open(event_file, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                        self._events.append(event)
                        event_id = event.get("id", 0)
                        if event_id:
                            self._event_index[event_id] = event  # 维护索引
                        self._event_counter = max(self._event_counter, event_id)
                    except json.JSONDecodeError as e:
                        logger.warning(
                            f"Failed to parse event in {event_file}: "
                            f"{type(e).__name__}: {str(e)[:50]}"
                        )
                        continue

            self._loaded = True
            logger.info(
                f"Loaded {len(self._events)} events for session {self.session_id}"
            )
        except OSError as e:
            logger.warning(
                f"Failed to load events from {event_file}: {type(e).__name__}: {e}"
            )

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
        """根据 ID 获取事件 (O(1) 查找)"""
        return self._event_index.get(event_id)

    def build_context_for_llm(
        self, system_prompt: str | None = None, max_recent_events: int | None = None
    ) -> list[dict[str, Any]]:
        """从事件流构建 LLM 上下文

        关键: 使用边界标记（摘要或上下文重置）而非截断历史

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

        # 2. 找到最近的边界标记（摘要或上下文重置）
        last_boundary = self.find_last_boundary_marker()

        # 3. 根据标记类型添加上下文
        if last_boundary:
            event_type = last_boundary["type"]
            data = last_boundary["data"]

            if event_type == EventType.SUMMARY_MARKER.value:
                # 摘要标记：添加摘要作为上下文
                summary_content = data.get("summary", "")
                messages.append(
                    {"role": "user", "content": f"[历史摘要]\n{summary_content}"}
                )
            elif event_type == EventType.CONTEXT_RESET.value:
                # 上下文重置标记：添加保留的上下文
                preserved = data.get("preserved_context")
                iteration = data.get("iteration", 0)
                if preserved:
                    messages.append(
                        {
                            "role": "system",
                            "content": f"[迭代 {iteration} 状态摘要]\n{preserved}",
                        }
                    )

        # 4. 获取边界点后的事件
        context_event_types: list[str | EventType] = [
            EventType.USER_INPUT,
            EventType.LLM_RESPONSE,
            EventType.TOOL_RESULT,
        ]

        # 使用边界标记后的起始 ID
        start_id = last_boundary["id"] + 1 if last_boundary else 0

        recent_events = self.get_events(start_id, event_types=context_event_types)

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

        return None

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
