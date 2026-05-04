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

from typing import TYPE_CHECKING

# 类型检查时使用真实类型，运行时根据条件导入
if TYPE_CHECKING:
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
else:
    # 运行时：尝试导入 OpenTelemetry，失败时使用 fallback
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

    except ImportError:
        # OpenTelemetry 未安装，使用 fallback NoOp 实现
        from typing import Any

        from .fallback import (
            SPAN_LLM_FALLBACK,
            SPAN_LLM_REQUEST,
            SPAN_SESSION,
            SPAN_SUBAGENT_EXECUTE,
            SPAN_TOOL_PREFIX,
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
        from .fallback import NoOpSpan as Span
        from .fallback import NoOpStatusCode as StatusCode

        # Attributes 类型 fallback
        Attributes = dict[str, Any]

        _OBSERVABILITY_ENABLED = False


# 导出启用状态标志
def is_observability_enabled() -> bool:
    """检查 OpenTelemetry 是否实际启用"""
    return _OBSERVABILITY_ENABLED


__all__ = [
    "SPAN_LLM_FALLBACK",
    "SPAN_LLM_REQUEST",
    # Constants
    "SPAN_SESSION",
    "SPAN_SUBAGENT_EXECUTE",
    "SPAN_TOOL_PREFIX",
    # Status
    "_OBSERVABILITY_ENABLED",
    "Attributes",
    # Types
    "Span",
    "StatusCode",
    "add_fallback_event",
    # Tracing
    "classify_error",
    "create_task_with_context",
    "get_meter",
    "get_tracer",
    "is_initialized",
    "is_observability_enabled",
    "record_llm_error",
    "record_llm_span_error",
    # Metrics
    "record_llm_success",
    "set_llm_span_attributes",
    "set_subagent_span_attributes",
    "set_tool_span_attributes",
    # Setup
    "setup_observability",
    "shutdown_observability",
    "start_as_current_span",
    "start_span",
    "traced",
]
