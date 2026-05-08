"""
Harness 单工具执行模块（无钩子版本）

执行单个工具并记录指标。

内容:
- execute_single_tool_with_metrics - 执行单个工具并记录指标
"""

import time
from collections import deque
from typing import TYPE_CHECKING, Any

from ._metrics import (
    ToolExecutionMetrics,
    create_tool_metric,
    finish_tool_span,
    start_tool_span,
)

if TYPE_CHECKING:
    from src.sandbox import Sandbox

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