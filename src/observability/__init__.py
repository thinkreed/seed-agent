"""
Seed-Agent OpenTelemetry 可观测性模块

公共接口导出，提供:
1. SDK 初始化 (setup_observability)
2. Metrics 记录 (record_llm_success, record_llm_error) - NoOp 实现
3. Tracing helpers (get_tracer, classify_error, etc.)

使用方式:
    from observability import setup_observability, get_tracer

    # 初始化
    setup_observability(otlp_endpoint="http://localhost:4318")

    # 创建 Span
    tracer = get_tracer()
    span = tracer.start_span("seed.llm.request")
"""

# Setup
from .setup import (
    setup_observability,
    get_tracer,
    get_meter,
    is_initialized,
    shutdown_observability,
)

# Metrics (NoOp 实现，因为 Jaeger OTLP Metrics 有兼容性问题)
from .metrics import (
    record_llm_success,
    record_llm_error,
)

# Tracing
from .tracing import (
    classify_error,
    record_llm_span_error,
    create_task_with_context,
    start_span,
    start_as_current_span,
    traced,
    add_fallback_event,
    set_llm_span_attributes,
    set_tool_span_attributes,
    set_subagent_span_attributes,
    SPAN_SESSION,
    SPAN_LLM_REQUEST,
    SPAN_LLM_FALLBACK,
    SPAN_TOOL_PREFIX,
    SPAN_SUBAGENT_EXECUTE,
)

# Re-export commonly used types
from opentelemetry.trace import Span, StatusCode
from opentelemetry.util.types import Attributes

__all__ = [
    # Setup
    "setup_observability",
    "get_tracer",
    "get_meter",
    "is_initialized",
    "shutdown_observability",
    # Metrics
    "record_llm_success",
    "record_llm_error",
    # Tracing
    "classify_error",
    "record_llm_span_error",
    "create_task_with_context",
    "start_span",
    "start_as_current_span",
    "traced",
    "add_fallback_event",
    "set_llm_span_attributes",
    "set_tool_span_attributes",
    "set_subagent_span_attributes",
    "SPAN_SESSION",
    "SPAN_LLM_REQUEST",
    "SPAN_LLM_FALLBACK",
    "SPAN_TOOL_PREFIX",
    "SPAN_SUBAGENT_EXECUTE",
    # Types
    "Span",
    "StatusCode",
    "Attributes",
]