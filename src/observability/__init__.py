"""Seed-Agent OpenTelemetry 可观测性模块"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opentelemetry.trace import Span, StatusCode
    from opentelemetry.util.types import Attributes
    from .metrics import record_llm_error, record_llm_success
    from .setup import get_meter, get_tracer, is_initialized, setup_observability, shutdown_observability
    from .tracing import SPAN_LLM_FALLBACK, SPAN_LLM_REQUEST, SPAN_SESSION, SPAN_SUBAGENT_EXECUTE, SPAN_TOOL_PREFIX, add_fallback_event, classify_error, create_task_with_context, record_llm_span_error, set_llm_span_attributes, set_subagent_span_attributes, set_tool_span_attributes, start_as_current_span, start_span, traced
    _OBSERVABILITY_ENABLED = True
else:
    try:
        from opentelemetry.trace import Span, StatusCode
        from opentelemetry.util.types import Attributes
        from .metrics import record_llm_error, record_llm_success
        from .setup import get_meter, get_tracer, is_initialized, setup_observability, shutdown_observability
        from .tracing import SPAN_LLM_FALLBACK, SPAN_LLM_REQUEST, SPAN_SESSION, SPAN_SUBAGENT_EXECUTE, SPAN_TOOL_PREFIX, add_fallback_event, classify_error, create_task_with_context, record_llm_span_error, set_llm_span_attributes, set_subagent_span_attributes, set_tool_span_attributes, start_as_current_span, start_span, traced
        _OBSERVABILITY_ENABLED = True
    except ImportError:
        from typing import Any
        from .fallback import SPAN_LLM_FALLBACK, SPAN_LLM_REQUEST, SPAN_SESSION, SPAN_SUBAGENT_EXECUTE, SPAN_TOOL_PREFIX, add_fallback_event, classify_error, create_task_with_context, get_meter, get_tracer, is_initialized, record_llm_error, record_llm_span_error, record_llm_success, set_llm_span_attributes, set_subagent_span_attributes, set_tool_span_attributes, setup_observability, shutdown_observability, start_as_current_span, start_span, traced
        from .fallback import NoOpSpan as Span
        from .fallback import NoOpStatusCode as StatusCode
        Attributes = dict[str, Any]
        _OBSERVABILITY_ENABLED = False


def is_observability_enabled() -> bool:
    """检查 OpenTelemetry 是否实际启用"""
    return _OBSERVABILITY_ENABLED


__all__ = ["SPAN_LLM_FALLBACK", "SPAN_LLM_REQUEST", "SPAN_SESSION", "SPAN_SUBAGENT_EXECUTE", "SPAN_TOOL_PREFIX", "_OBSERVABILITY_ENABLED", "Attributes", "Span", "StatusCode", "add_fallback_event", "classify_error", "create_task_with_context", "get_meter", "get_tracer", "is_initialized", "is_observability_enabled", "record_llm_error", "record_llm_span_error", "record_llm_success", "set_llm_span_attributes", "set_subagent_span_attributes", "set_tool_span_attributes", "setup_observability", "shutdown_observability", "start_as_current_span", "start_span", "traced"]