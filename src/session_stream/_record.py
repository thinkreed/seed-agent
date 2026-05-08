"""
Session 事件记录辅助方法

提供便捷的事件记录方法，封装常用的事件类型。
"""

from typing import Any

from src.session_stream._types import EventType


def record_session_start(
    emit_event_func,
    metadata: dict[str, Any] | None = None,
) -> int:
    """记录会话开始事件

    Args:
        emit_event_func: 事件发射函数 (emit_event)
        metadata: 会话元数据

    Returns:
        事件 ID
    """
    return emit_event_func(EventType.SESSION_START, {"metadata": metadata or {}})


def record_session_end(
    emit_event_func,
    event_count: int,
    reason: str = "normal",
) -> int:
    """记录会话结束事件

    Args:
        emit_event_func: 事件发射函数 (emit_event)
        event_count: 当前事件总数
        reason: 结束原因

    Returns:
        事件 ID
    """
    return emit_event_func(
        EventType.SESSION_END,
        {"reason": reason, "event_count": event_count},
    )


def record_error(
    emit_event_func,
    error_type: str,
    error_message: str,
    context: dict[str, Any] | None = None,
) -> int:
    """记录错误事件

    Args:
        emit_event_func: 事件发射函数 (emit_event)
        error_type: 错误类型
        error_message: 错误消息
        context: 错误上下文

    Returns:
        事件 ID
    """
    return emit_event_func(
        EventType.ERROR_OCCURRED,
        {
            "error_type": error_type,
            "error_message": error_message,
            "context": context or {},
        },
    )