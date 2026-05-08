"""
OpenTelemetry Fallback 实现

当 OpenTelemetry 未安装时，提供 NoOp 实现以确保代码正常运行。
所有核心模块只需从 observability 导入，无需单独处理 ImportError。

使用方式:
    from src.observability import get_tracer, SPAN_SESSION, StatusCode
    # 自动处理 ImportError，返回 NoOp 实现
"""

from ._constants import (
    SPAN_LLM_FALLBACK,
    SPAN_LLM_REQUEST,
    SPAN_SESSION,
    SPAN_SUBAGENT_EXECUTE,
    SPAN_TOOL_PREFIX,
)
from ._fallback_api import (
    add_fallback_event,
    classify_error,
    create_task_with_context,
    get_meter,
    get_tracer,
    is_initialized,
    record_llm_error,
    record_llm_span_error,
    record_llm_success,
    set_llm_span_attributes,
    set_subagent_span_attributes,
    set_tool_span_attributes,
    setup_observability,
    shutdown_observability,
    start_as_current_span,
    start_span,
    traced,
)
from ._noop import NoOpSpan, NoOpStatusCode, NoOpTracer, SpanAttributeValue

__all__ = [
    "SPAN_LLM_FALLBACK",
    "SPAN_LLM_REQUEST",
    "SPAN_SESSION",
    "SPAN_SUBAGENT_EXECUTE",
    "SPAN_TOOL_PREFIX",
    "NoOpSpan",
    "NoOpStatusCode",
    "NoOpTracer",
    "SpanAttributeValue",
    "add_fallback_event",
    "classify_error",
    "create_task_with_context",
    "get_meter",
    "get_tracer",
    "is_initialized",
    "record_llm_error",
    "record_llm_span_error",
    "record_llm_success",
    "set_llm_span_attributes",
    "set_subagent_span_attributes",
    "set_tool_span_attributes",
    "setup_observability",
    "shutdown_observability",
    "start_as_current_span",
    "start_span",
    "traced",
]