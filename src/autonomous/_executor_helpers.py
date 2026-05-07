"""任务执行辅助方法模块

包含 TaskExecutor 的辅助方法：
- _reset_context_if_needed
- _handle_response
- _notify_completion
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from src.autonomous._executor_constants import (
    CONTEXT_RESET_ENABLED,
    CONTEXT_RESET_INTERVAL,
)
from src.autonomous._prompt_builder import (
    extract_autonomous_prompt_core,
)
from src.ralph_state import extract_critical_context
from src.session_event_stream import EventType

if TYPE_CHECKING:
    from src.autonomous._executor_core import TaskExecutor

logger = logging.getLogger("seed_agent")


async def reset_context_if_needed(executor: "TaskExecutor") -> str | None:
    """条件性重置上下文（防止上下文漂移）

    Args:
        executor: TaskExecutor 实例

    Returns:
        重置后的上下文，或 None 表示未重置
    """
    if not CONTEXT_RESET_ENABLED:
        return None

    iteration = executor._state_manager.get_iteration_count()
    if iteration % CONTEXT_RESET_INTERVAL != 0:
        return None

    # 提取关键上下文
    history_context = extract_critical_context(executor.agent.history) or ""

    # 保留自主探索的核心指令
    autonomous_prompt = executor.agent.system_prompt or ""
    preserved_autonomous = extract_autonomous_prompt_core(
        autonomous_prompt, executor._sop_content
    )

    # 合并
    preserved = (
        f"{preserved_autonomous}\n\n---\n\n{history_context}"
        if history_context
        else preserved_autonomous
    )

    # 通过 Session 创建上下文重置标记
    executor.agent.session.create_context_reset_marker(
        iteration=iteration, preserved_context=preserved
    )

    logger.info(f"Context reset marker created at iteration {iteration}")
    return preserved


async def handle_response(executor: "TaskExecutor", response: str | None) -> str | None:
    """处理响应并返回下一轮的 prompt

    Args:
        executor: TaskExecutor 实例
        response: 当前响应

    Returns:
        下一轮执行的 prompt，或 None 表示不继续
    """
    if not response:
        executor._state_manager.increment_empty_response()
        logger.warning(
            f"Empty response at iteration {executor._state_manager.get_iteration_count()} "
            f"(count: {executor._state_manager.get_empty_response_count()})"
        )
        if executor._state_manager.get_empty_response_count() >= 3:
            logger.warning("Too many empty responses, trying simplified prompt")
            return "请报告当前状态"
        return "继续执行自主探索任务，请报告进展"
    return None


async def notify_completion(
    executor: "TaskExecutor",
    result: str,
) -> None:
    """通知探索完成

    Args:
        executor: TaskExecutor 实例
        result: 执行结果
    """
    if executor.on_explore_complete:
        if asyncio.iscoroutinefunction(executor.on_explore_complete):
            await executor.on_explore_complete(result)
        else:
            executor.on_explore_complete(result)


def record_tool_calls(executor: "TaskExecutor") -> None:
    """记录工具调用历史（从 Session 获取最近的工具调用）

    Args:
        executor: TaskExecutor 实例
    """
    iteration = executor._state_manager.get_iteration_count()
    recent_events = executor.agent.session.get_events(start_id=-5)
    for event in recent_events:
        if event["type"] == EventType.TOOL_CALL.value:
            tool_data = event.get("data", {})
            executor._defense.add_action(tool_data.get("tool_name", ""), iteration)


__all__ = [
    "handle_response",
    "notify_completion",
    "record_tool_calls",
    "reset_context_if_needed",
]