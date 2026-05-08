"""
Harness 单工具执行模块（带生命周期钩子）

执行单个工具并触发生命周期钩子。
"""

import json
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
        harness: Harness 实例
        sandbox: Sandbox 实例
        hook_registry: 钩子注册中心
        metrics_deque: 指标存储 deque

    Returns:
        执行结果字典
    """
    tool_name = tool_call.get("function", {}).get("name", "unknown")
    raw_args = tool_call.get("function", {}).get("arguments", "{}")
    tool_call_id = tool_call.get("id", "unknown")

    tool_args = parse_tool_arguments(raw_args)
    if is_parse_failed(tool_args):
        return {"tool_call_id": tool_call_id, "role": "tool",
                "content": "Error: Failed to parse arguments: invalid JSON"}

    # 触发 tool_call_before 钩子
    before_ctx = build_tool_call_before_ctx(
        session, harness, sandbox, tool_name, tool_args, tool_call_id)
    await trigger_hook(hook_registry, HookPoint.TOOL_CALL_BEFORE, before_ctx)

    actual_args = before_ctx.get("mapped_args", tool_args)
    start_time = time.time()
    span = start_tool_span(tool_name, actual_args)

    try:
        result = await sandbox.execute_tools(
            [{"id": tool_call_id, "function": {
                "name": tool_name, "arguments": json.dumps(actual_args)}}])
        duration_ms = (time.time() - start_time) * 1000

        tool_result = result[0] if result else {
            "tool_call_id": tool_call_id, "role": "tool",
            "content": "Error: No result returned"}

        metrics_deque.append(create_tool_metric(tool_name, duration_ms, success=True))
        finish_tool_span(span, start_time, success=True)

        # 触发 tool_call_after 钩子
        after_ctx = build_tool_call_after_ctx(
            session, harness, sandbox, tool_name, actual_args, tool_call_id,
            tool_result.get("content", ""), duration_ms, success=True)
        await trigger_hook(hook_registry, HookPoint.TOOL_CALL_AFTER, after_ctx)

        return tool_result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        err_msg = str(e)[:200]

        metrics_deque.append(
            create_tool_metric(tool_name, duration_ms, success=False, error=err_msg))
        finish_tool_span(span, start_time, success=False, error=e)

        error_ctx = build_tool_call_error_ctx(
            session, harness, sandbox, tool_name, tool_call_id,
            actual_args, str(e), duration_ms)
        await trigger_hook(hook_registry, HookPoint.TOOL_CALL_ERROR, error_ctx)

        return {"tool_call_id": tool_call_id, "role": "tool",
                "content": f"Error: {type(e).__name__}: {err_msg}"}