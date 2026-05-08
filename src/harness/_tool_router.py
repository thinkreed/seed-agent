"""
Harness 工具路由模块

提取工具路由逻辑。

内容:
- route_tool_calls - 路由工具调用到 Sandbox
- route_tool_calls_with_hooks - 路由工具调用（带钩子）
"""

import logging
from typing import TYPE_CHECKING, Any

from src.session_event_stream import EventType

from ._tool_executor import execute_tools_parallel, execute_tools_parallel_with_hooks

# Re-export for API compatibility (harness.py imports execute_tools_parallel_with_hooks)
__all__ = [
    "execute_tools_parallel",
    "execute_tools_parallel_with_hooks",
    "route_tool_calls",
    "route_tool_calls_with_hooks",
]

if TYPE_CHECKING:
    from src.sandbox import Sandbox
    from src.session_event_stream import SessionEventStream

logger = logging.getLogger(__name__)


async def route_tool_calls(
    tool_calls: list[dict[str, Any]],
    session: "SessionEventStream",
    sandbox: "Sandbox",
) -> list[dict[str, Any]]:
    """路由工具调用到 Sandbox（无钩子版本）

    Args:
        tool_calls: 工具调用列表
        session: SessionEventStream 实例
        sandbox: Sandbox 实例

    Returns:
        工具执行结果列表
    """
    logger.debug(f"Routing {len(tool_calls)} tool calls to Sandbox")

    # 记录工具调用事件
    for tc in tool_calls:
        session.emit_event(
            EventType.TOOL_CALL,
            {
                "tool_call_id": tc.get("id"),
                "tool_name": tc.get("function", {}).get("name"),
                "arguments": tc.get("function", {}).get("arguments"),
            },
        )

    # 并发执行工具调用
    return await execute_tools_parallel(tool_calls, sandbox)


async def route_tool_calls_with_hooks(
    tool_calls: list[dict[str, Any]],
    session: "SessionEventStream",
    harness: Any,
    sandbox: "Sandbox",
    hook_registry: Any,
    metrics_deque: Any,
) -> list[dict[str, Any]]:
    """路由工具调用到 Sandbox（带生命周期钩子）

    Args:
        tool_calls: 工具调用列表
        session: SessionEventStream 实例
        harness: Harness 实例
        sandbox: Sandbox 实例
        hook_registry: 钩子注册中心
        metrics_deque: 指标存储 deque

    Returns:
        工具执行结果列表
    """
    logger.debug(f"Routing {len(tool_calls)} tool calls to Sandbox (with hooks)")

    # 记录工具调用事件
    for tc in tool_calls:
        session.emit_event(
            EventType.TOOL_CALL,
            {
                "tool_call_id": tc.get("id"),
                "tool_name": tc.get("function", {}).get("name"),
                "arguments": tc.get("function", {}).get("arguments"),
            },
        )

    # 并发执行工具调用（带钩子）
    return await execute_tools_parallel_with_hooks(
        tool_calls, session, harness, sandbox, hook_registry, metrics_deque
    )