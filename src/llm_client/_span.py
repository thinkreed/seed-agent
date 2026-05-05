"""LLMClient OpenTelemetry 辅助模块

Span 创建和完成辅助函数
"""

import logging
import time
from typing import Any

from src.observability import StatusCode, get_tracer, is_observability_enabled

logger = logging.getLogger(__name__)

_OBSERVABILITY_ENABLED = is_observability_enabled()


try:
    from opentelemetry.trace import Span
except ImportError:
    Span = None  # type: ignore[misc,assignment]


def is_observability_available() -> bool:
    """检查 OpenTelemetry 是否可用"""
    return _OBSERVABILITY_ENABLED and get_tracer() is not None


def start_llm_span(
    model_id: str,
    context: list[dict[str, Any]],
    tools: list[dict] | None,
    is_stream: bool = False,
) -> "Span | None":
    """创建 LLM Span"""
    tracer = get_tracer()
    if not (tracer and _OBSERVABILITY_ENABLED):
        return None

    span = tracer.start_span("seed.llm.reason")
    span.set_attribute("seed.llm.model_id", model_id)
    span.set_attribute("seed.llm.context_length", len(context))
    span.set_attribute("seed.llm.tools_count", len(tools) if tools else 0)
    span.set_attribute("seed.llm.is_stream", is_stream)
    return span


def finish_llm_span(
    span: "Span | None",
    start_time: float,
    success: bool,
    error: Exception | None = None,
) -> None:
    """完成 LLM Span"""
    if not span:
        return

    duration_ms = (time.time() - start_time) * 1000
    span.set_attribute("seed.llm.duration_ms", duration_ms)

    if success:
        span.set_status(StatusCode.OK)
    elif error:
        span.record_exception(error)
        span.set_attribute("seed.error.message", str(error)[:500])
        span.set_status(StatusCode.ERROR, str(error)[:200])
    span.end()