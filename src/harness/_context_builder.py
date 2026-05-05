"""
Harness 上下文构建模块

提取上下文构建逻辑（上下文工程）。

内容:
- build_context_from_session - 从 Session 构建优化上下文
- build_context_from_session_async - 异步构建优化上下文
- get_events_since_last_summary - 获取最近摘要之后的事件
"""

import logging
from typing import TYPE_CHECKING, Any

from src.session_event_stream import EventType

if TYPE_CHECKING:
    from src.context_engineering import ContextEngineering
    from src.session_event_stream import SessionEventStream

logger = logging.getLogger(__name__)


def build_context_from_session(
    session: "SessionEventStream",
    context_engineering: "ContextEngineering | None",
    context_window: int,
    current_task: str | None,
    system_prompt: str | None,
    enable_pruning: bool,
) -> list[dict[str, Any]]:
    """从 Session 构建优化上下文（上下文工程）

    流程：
    1. 如有 ContextEngineering 实例，使用渐进式压缩 + 智能裁剪
    2. 否则使用 Session 原生方法（摘要标记机制）

    Args:
        session: SessionEventStream 实例
        context_engineering: 上下文工程实例（可选）
        context_window: 上下文窗口大小
        current_task: 当前任务描述（用于智能裁剪）
        system_prompt: 系统提示
        enable_pruning: 是否启用智能裁剪

    Returns:
        messages 格式的优化上下文
    """
    if context_engineering:
        # 使用上下文工程优化
        return context_engineering.build_optimized_context(
            session=session,
            context_window=context_window,
            current_task=current_task,
            system_prompt=system_prompt,
            enable_pruning=enable_pruning,
        )

    # 无上下文工程时，使用 Session 原生方法
    return session.build_context_for_llm(system_prompt=system_prompt)


async def build_context_from_session_async(
    session: "SessionEventStream",
    context_engineering: "ContextEngineering | None",
    context_window: int,
    current_task: str | None,
    system_prompt: str | None,
    enable_pruning: bool,
    enable_semantic_pruning: bool = False,
) -> list[dict[str, Any]]:
    """异步构建优化上下文（支持 LLM 摘要）

    Args:
        session: SessionEventStream 实例
        context_engineering: 上下文工程实例（可选）
        context_window: 上下文窗口大小
        current_task: 当前任务描述
        system_prompt: 系统提示
        enable_pruning: 是否启用智能裁剪
        enable_semantic_pruning: 是否启用语义裁剪（LLM）

    Returns:
        messages 格式的优化上下文
    """
    if context_engineering:
        return await context_engineering.build_optimized_context_async(
            session=session,
            context_window=context_window,
            current_task=current_task,
            system_prompt=system_prompt,
            enable_pruning=enable_pruning,
            enable_semantic_pruning=enable_semantic_pruning,
        )

    return session.build_context_for_llm(system_prompt=system_prompt)


def get_events_since_last_summary(
    session: "SessionEventStream",
) -> list[dict[str, Any]]:
    """获取最近摘要标记之后的事件

    Args:
        session: SessionEventStream 实例

    Returns:
        事件列表
    """
    return session.get_events_since_last_summary(
        [EventType.USER_INPUT, EventType.LLM_RESPONSE, EventType.TOOL_RESULT]
    )