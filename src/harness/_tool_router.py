"""
Harness 工具路由模块

提取工具路由和并发执行逻辑。

内容:
- route_tool_calls - 路由工具调用到 Sandbox
- route_tool_calls_with_hooks - 路由工具调用（带钩子）
- execute_tools_parallel - 并发执行工具（无钩子）
- execute_tools_parallel_with_hooks - 并发执行工具（带钩子）
"""

import asyncio
import logging
from collections import deque
from typing import TYPE_CHECKING, Any

from src.lifecycle_hooks import HookPoint
from src.session_event_stream import EventType

from ._lifecycle_hooks import trigger_hook
from ._metrics import ToolExecutionMetrics
from ._single_tool import execute_single_tool_with_hooks
from ._write_conflict import check_write_conflicts

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
    metrics_deque: deque[ToolExecutionMetrics],
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


async def execute_tools_parallel(
    tool_calls: list[dict[str, Any]],
    sandbox: "Sandbox",
) -> list[dict[str, Any]]:
    """并发执行工具调用（无钩子版本）

    注意：此方法已弃用，推荐使用 execute_tools_parallel_with_hooks。
    为保持向后兼容保留此方法，内部调用带钩子版本。

    Args:
        tool_calls: 工具调用列表
        sandbox: Sandbox 实例

    Returns:
        工具执行结果列表
    """
    results = await sandbox.execute_tools(tool_calls)
    return results if results else []


async def execute_tools_parallel_with_hooks(
    tool_calls: list[dict[str, Any]],
    session: "SessionEventStream",
    harness: Any,
    sandbox: "Sandbox",
    hook_registry: Any,
    metrics_deque: deque[ToolExecutionMetrics],
) -> list[dict[str, Any]]:
    """并发执行工具调用（带生命周期钩子）

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
    # 检查并发写冲突
    conflict_result = check_write_conflicts(tool_calls)
    if conflict_result:
        return conflict_result

    # 并发执行（每个工具带钩子）
    results = await asyncio.gather(
        *[
            execute_single_tool_with_hooks(
                tc, session, harness, sandbox, hook_registry, metrics_deque
            )
            for tc in tool_calls
        ],
        return_exceptions=True,
    )

    processed_results: list[dict[str, Any]] = []
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            if isinstance(result, Exception):
                raise result

            tool_name = tool_calls[i].get("function", {}).get("name", "unknown")
            logger.error(
                f"Tool {tool_name} failed: {type(result).__name__}: {result}"
            )

            # 触发 tool_call_error 钩子
            error_ctx = {
                "session": session,
                "harness": harness,
                "tool_name": tool_name,
                "tool_call_id": tool_calls[i].get("id", "unknown"),
                "tool_args": {},
                "error": str(result)[:500],
            }
            await trigger_hook(hook_registry, HookPoint.TOOL_CALL_ERROR, error_ctx)

            processed_results.append(
                {
                    "tool_call_id": tool_calls[i].get("id", "unknown"),
                    "role": "tool",
                    "content": f"Error: {type(result).__name__}: {str(result)[:200]}",
                }
            )
        elif isinstance(result, dict):
            processed_results.append(result)
        else:
            logger.warning(f"Unexpected result type: {type(result).__name__}")
            processed_results.append(
                {
                    "tool_call_id": tool_calls[i].get("id", "unknown"),
                    "role": "tool",
                    "content": "Error: Unexpected result type",
                }
            )

    return processed_results