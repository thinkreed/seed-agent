"""
Harness 指标模块

提取工具执行指标类型和 OpenTelemetry Span 管理。

内容:
- ToolExecutionMetrics TypedDict
- start_tool_span / finish_tool_span 函数
- observability 状态检查
"""

import time
from typing import Any, TypedDict

from src.observability import (
    SPAN_TOOL_PREFIX,
    StatusCode,
    get_tracer,
    is_observability_enabled,
    set_tool_span_attributes,
)

try:
    from opentelemetry.trace import Span
except ImportError:
    Span = None  # type: ignore[misc,assignment]

# OpenTelemetry 状态（模块级常量）
OBSERVABILITY_ENABLED = is_observability_enabled()


class ToolExecutionMetrics(TypedDict):
    """工具执行指标

    Attributes:
        tool_name: 工具名称
        duration_ms: 执行时长（毫秒）
        success: 是否成功
        error: 错误信息（可选）
    """

    tool_name: str
    duration_ms: float
    success: bool
    error: str | None


def start_tool_span(tool_name: str, tool_args: dict[str, Any]) -> "Span | None":
    """创建工具 Span

    Args:
        tool_name: 工具名称
        tool_args: 工具参数（用于提取 file_path 等属性）

    Returns:
        OpenTelemetry Span 或 None（如果 observability 未启用）
    """
    tracer = get_tracer()
    if not (tracer and OBSERVABILITY_ENABLED):
        return None

    span = tracer.start_span(f"{SPAN_TOOL_PREFIX}{tool_name}")
    set_tool_span_attributes(span, tool_name, file_path=tool_args.get("path", ""))
    return span


def finish_tool_span(
    span: "Span | None",
    start_time: float,
    success: bool,
    error: Exception | None = None,
) -> None:
    """完成 Span

    Args:
        span: OpenTelemetry Span（可为 None）
        start_time: 开始时间（用于计算 duration）
        success: 是否成功
        error: 错误信息（可选）
    """
    if not span:
        return

    duration_ms = (time.time() - start_time) * 1000
    if success:
        span.set_attribute("seed.tool.duration_ms", duration_ms)
        span.set_status(StatusCode.OK)
    elif error:
        span.record_exception(error)
        span.set_attribute("seed.error.message", str(error)[:500])
        span.set_status(StatusCode.ERROR, str(error)[:200])
    span.end()


def create_tool_metric(
    tool_name: str,
    duration_ms: float,
    success: bool,
    error: str | None = None,
) -> ToolExecutionMetrics:
    """创建工具执行指标

    Args:
        tool_name: 工具名称
        duration_ms: 执行时长（毫秒）
        success: 是否成功
        error: 错误信息（可选）

    Returns:
        ToolExecutionMetrics TypedDict
    """
    return {
        "tool_name": tool_name,
        "duration_ms": duration_ms,
        "success": success,
        "error": error,
    }