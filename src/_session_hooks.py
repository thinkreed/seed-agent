"""
会话生命周期钩子

包含：
- 会话生命周期钩子：session_start, session_end, session_pause, session_resume
- 上下文钩子：context_reset_before, context_reset_after, summary_generated
"""

import logging
from typing import Any

from src.lifecycle_hooks import HookPoint, LifecycleHookRegistry

logger = logging.getLogger(__name__)


def register_session_hooks(registry: LifecycleHookRegistry) -> None:
    """注册会话生命周期钩子"""

    @registry.register(HookPoint.SESSION_START, priority=0, name="session_log_start")
    def session_log_start(context: dict[str, Any]) -> None:
        """记录会话开始"""
        session_id = context.get("session_id", "unknown")
        metadata = context.get("metadata", {})
        logger.info(f"Session started: {session_id}, metadata={metadata}")

    @registry.register(HookPoint.SESSION_START, priority=1, name="session_init_state")
    def session_init_state(context: dict[str, Any]) -> None:
        """初始化会话状态"""
        session = context.get("session")
        if session:
            context["session_state"] = {
                "event_count": 0,
                "conversation_rounds": 0,
            }

    @registry.register(HookPoint.SESSION_END, priority=0, name="session_log_end")
    def session_log_end(context: dict[str, Any]) -> None:
        """记录会话结束"""
        session_id = context.get("session_id", "unknown")
        reason = context.get("reason", "normal")
        event_count = context.get("event_count", 0)
        logger.info(
            f"Session ended: {session_id}, reason={reason}, events={event_count}"
        )

    @registry.register(HookPoint.SESSION_END, priority=1, name="session_persist_state")
    def session_persist_state(context: dict[str, Any]) -> None:
        """持久化会话状态"""
        session = context.get("session")
        if session and hasattr(session, "persist_state"):
            # 调用会话持久化方法（如果存在）
            pass  # 实际持久化由 SessionEventStream 完成

    @registry.register(HookPoint.SESSION_PAUSE, priority=0, name="session_log_pause")
    def session_log_pause(context: dict[str, Any]) -> None:
        """记录会话暂停"""
        session_id = context.get("session_id", "unknown")
        logger.info(f"Session paused: {session_id}")

    @registry.register(HookPoint.SESSION_RESUME, priority=0, name="session_log_resume")
    def session_log_resume(context: dict[str, Any]) -> None:
        """记录会话恢复"""
        session_id = context.get("session_id", "unknown")
        logger.info(f"Session resumed: {session_id}")


def register_context_hooks(registry: LifecycleHookRegistry) -> None:
    """注册上下文钩子"""

    @registry.register(
        HookPoint.CONTEXT_RESET_BEFORE, priority=0, name="context_log_reset"
    )
    def context_log_reset(context: dict[str, Any]) -> None:
        """记录上下文重置"""
        reason = context.get("reason", "unknown")
        event_count = context.get("event_count", 0)

        logger.info(f"Context reset: reason={reason}, events={event_count}")

    @registry.register(
        HookPoint.CONTEXT_RESET_BEFORE, priority=1, name="context_extract_critical"
    )
    def context_extract_critical(context: dict[str, Any]) -> None:
        """提取关键上下文"""
        history = context.get("history", [])

        # 提取最后几条关键消息
        critical_messages = history[-5:] if len(history) > 5 else history
        context["critical_context"] = critical_messages

    @registry.register(
        HookPoint.CONTEXT_RESET_AFTER, priority=0, name="context_inject_preserved"
    )
    def context_inject_preserved(context: dict[str, Any]) -> None:
        """注入保留上下文"""
        preserved = context.get("preserved_context")
        history = context.get("history")

        if preserved and history is not None:
            # 添加状态摘要作为系统消息
            history.append({"role": "system", "content": f"[状态摘要]\n{preserved}"})

    @registry.register(HookPoint.SUMMARY_GENERATED, priority=0, name="summary_log")
    def summary_log(context: dict[str, Any]) -> None:
        """记录摘要生成"""
        summary = context.get("summary", "")
        covers_events = context.get("covers_events", [])

        logger.info(
            f"Summary generated: covers {len(covers_events)} events, "
            f"length={len(summary)}"
        )

    @registry.register(HookPoint.SUMMARY_GENERATED, priority=1, name="summary_record")
    def summary_record(context: dict[str, Any]) -> None:
        """记录摘要到会话"""
        session = context.get("session")
        summary = context.get("summary", "")

        if session and hasattr(session, "create_summary_marker"):
            event_count = session.get_event_count()
            session.create_summary_marker(event_count, summary)