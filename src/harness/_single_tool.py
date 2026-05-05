"""
Harness 单工具执行模块

提取单工具执行逻辑（带生命周期钩子和指标）。

内容:
- execute_single_tool_with_hooks - 执行单个工具（带钩子）
- execute_single_tool_with_metrics - 执行单个工具并记录指标
"""

import json
import logging
import time
from collections import deque
from typing import TYPE_CHECKING, Any

from src.lifecycle_hooks import HookPoint
from src.tools.utils import is_parse_failed, parse_tool_arguments

from ._lifecycle_hooks import (
    build_tool_call_after_ctx,
    build_tool_call_before_ctx,
    build_tool_call_error_ctx,
    trigger_hook,
)
from ._metrics import (
    ToolExecutionMetrics,
    create_tool_metric,
    finish_tool_span,
    start_tool_span,
)

if TYPE_CHECKING:
    from src.sandbox import Sandbox
    from src.session_event_stream import SessionEventStream

logger = logging.getLogger(__name__)


async def execute_single_tool_with_hooks(
    tool_call: dict[str, Any],
    session: "SessionEventStream",
    harness: Any,
    sandbox: "Sandbox",
    hook_registry: Any,
    metrics_deque: deque[ToolExecutionMetrics],
) -> dict[str, Any]:
    """执行单个工具（带生命周期钩子）

    Args:
        tool_call: 工具调用请求
        session: SessionEventStream 实例
        harness: Harness 实例（用于钩子上下文）
        sandbox: Sandbox 实例
        hook_registry: 钩子注册中心
        metrics_deque: 指标存储 deque

    Returns:
        执行结果字典
    """
    tool_name = tool_call.get("function", {}).get("name", "unknown")
    raw_args = tool_call.get("function", {}).get("arguments", "{}")
    tool_call_id = tool_call.get("id", "unknown")

    # 使用统一函数解析参数
    tool_args = parse_tool_arguments(raw_args)
    if is_parse_failed(tool_args):
        return {
            "tool_call_id": tool_call_id,
            "role": "tool",
            "content": "Error: Failed to parse arguments: invalid JSON",
        }

    # 1. 触发 tool_call_before 钩子
    before_ctx = build_tool_call_before_ctx(
        session, harness, sandbox, tool_name, tool_args, tool_call_id
    )
    await trigger_hook(hook_registry, HookPoint.TOOL_CALL_BEFORE, before_ctx)

    # 使用映射后的参数（如果钩子修改了）
    actual_args = before_ctx.get("mapped_args", tool_args)

    start_time = time.time()
    span = start_tool_span(tool_name, actual_args)

    try:
        # 2. 执行工具
        result = await sandbox.execute_tools(
            [
                {
                    "id": tool_call_id,
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(actual_args),
                    },
                }
            ]
        )
        duration_ms = (time.time() - start_time) * 1000

        tool_result = (
            result[0]
            if result
            else {
                "tool_call_id": tool_call_id,
                "role": "tool",
                "content": "Error: No result returned",
            }
        )

        # 记录指标
        metrics_deque.append(
            create_tool_metric(tool_name, duration_ms, success=True)
        )

        finish_tool_span(span, start_time, success=True)

        # 3. 触发 tool_call_after 钩子
        after_ctx = build_tool_call_after_ctx(
            session,
            harness,
            sandbox,
            tool_name,
            actual_args,
            tool_call_id,
            tool_result.get("content", ""),
            duration_ms,
            success=True,
        )
        await trigger_hook(hook_registry, HookPoint.TOOL_CALL_AFTER, after_ctx)

        return tool_result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000

        # 记录指标
        metrics_deque.append(
            create_tool_metric(tool_name, duration_ms, success=False, error=str(e)[:200])
        )

        finish_tool_span(span, start_time, success=False, error=e)

        # 触发 tool_call_error 钩子
        error_ctx = build_tool_call_error_ctx(
            session,
            harness,
            sandbox,
            tool_name,
            tool_call_id,
            actual_args,
            str(e),
            duration_ms,
        )
        await trigger_hook(hook_registry, HookPoint.TOOL_CALL_ERROR, error_ctx)

        return {
            "tool_call_id": tool_call_id,
            "role": "tool",
            "content": f"Error: {type(e).__name__}: {str(e)[:200]}",
        }


async def execute_single_tool_with_metrics(
    tool_call: dict[str, Any],
    sandbox: "Sandbox",
    metrics_deque: deque[ToolExecutionMetrics],
) -> dict[str, Any]:
    """执行单个工具并记录指标（无钩子版本）

    Args:
        tool_call: 工具调用请求
        sandbox: Sandbox 实例
        metrics_deque: 指标存储 deque

    Returns:
        执行结果字典
    """
    tool_name = tool_call.get("function", {}).get("name", "unknown")
    start_time = time.time()

    # OpenTelemetry Span
    span = start_tool_span(tool_name, {})

    try:
        result = await sandbox.execute_tools([tool_call])
        duration_ms = (time.time() - start_time) * 1000

        # 记录指标
        metrics_deque.append(
            create_tool_metric(tool_name, duration_ms, success=True)
        )

        finish_tool_span(span, start_time, success=True)

        return (
            result[0]
            if result
            else {
                "tool_call_id": tool_call.get("id"),
                "role": "tool",
                "content": "Error: No result returned",
            }
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000

        metrics_deque.append(
            create_tool_metric(tool_name, duration_ms, success=False, error=str(e)[:200])
        )

        finish_tool_span(span, start_time, success=False, error=e)

        return {
            "tool_call_id": tool_call.get("id"),
            "role": "tool",
            "content": f"Error: {type(e).__name__}: {str(e)[:200]}",
        }