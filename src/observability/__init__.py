"""
Seed-Agent OpenTelemetry 可观测性模块

公共接口导出，提供:
1. SDK 初始化 (setup_observability)
2. Metrics 记录 (record_llm_success, record_llm_error)
3. Tracing helpers (get_tracer, classify_error, etc.)

自动处理 ImportError:
- 当 OpenTelemetry 未安装时，自动使用 NoOp 实现
- 其他模块只需直接导入，无需单独处理 ImportError

使用方式:
    from src.observability import setup_observability, get_tracer, SPAN_SESSION, StatusCode

    # 初始化（可选）
    setup_observability(otlp_endpoint="http://localhost:4318")

    # 创建 Span - 自动处理 NoOp
    tracer = get_tracer()
    span = tracer.start_span("seed.llm.request")
"""

# 尝试导入 OpenTelemetry，失败时使用 fallback
try:
    # Re-export commonly used types
    from opentelemetry.trace import Span, StatusCode
    from opentelemetry.util.types import Attributes

    # Metrics
    from .metrics import (
        record_llm_error,
        record_llm_success,
    )
    # Setup
    from .setup import (
        get_meter,
        get_tracer,
        is_initialized,
        setup_observability,
        shutdown_observability,
    )
    # Tracing
    from .tracing import (
        SPAN_LLM_FALLBACK,
        SPAN_LLM_REQUEST,
        SPAN_SESSION,
        SPAN_SUBAGENT_EXECUTE,
        SPAN_TOOL_PREFIX,
        add_fallback_event,
        classify_error,
        create_task_with_context,
        record_llm_span_error,
        set_llm_span_attributes,
        set_subagent_span_attributes,
        set_tool_span_attributes,
        start_as_current_span,
        start_span,
        traced,
    )

    _OBSERVABILITY_ENABLED = True

except ImportError:  # type: ignore[misc]
    # OpenTelemetry 未安装，使用 fallback NoOp 实现
    # 所有导入的类型不匹配是预期的，因为我们使用 NoOp 实现
    from typing import Any

    from .fallback import (  # type: ignore[misc,assignment]
        # Types
        NoOpSpan as Span,
        NoOpStatusCode as StatusCode,
        # Constants
        SPAN_LLM_FALLBACK,
        SPAN_LLM_REQUEST,
        SPAN_SESSION,
        SPAN_SUBAGENT_EXECUTE,
        SPAN_TOOL_PREFIX,
        # Functions
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

    # Attributes 类型 fallback
    Attributes = dict[str, Any]  # type: ignore[misc]

    _OBSERVABILITY_ENABLED = False


# 导出启用状态标志
def is_observability_enabled() -> bool:
    """检查 OpenTelemetry 是否实际启用"""
    return _OBSERVABILITY_ENABLED


__all__ = [
    # Setup
    "setup_observability",
    "get_tracer",
    "get_meter",
    "is_initialized",
    "is_observability_enabled",
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
    # Constants
    "SPAN_SESSION",
    "SPAN_LLM_REQUEST",
    "SPAN_LLM_FALLBACK",
    "SPAN_TOOL_PREFIX",
    "SPAN_SUBAGENT_EXECUTE",
    # Types
    "Span",
    "StatusCode",
    "Attributes",
    # Status
    "_OBSERVABILITY_ENABLED",
]