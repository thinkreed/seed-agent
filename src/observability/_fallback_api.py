"""Fallback API 函数 - NoOp 实现确保无 OpenTelemetry 时正常运行"""

import asyncio
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, TypeVar

from ._constants import (
    SPAN_LLM_FALLBACK,
    SPAN_LLM_REQUEST,
    SPAN_SESSION,
    SPAN_SUBAGENT_EXECUTE,
    SPAN_TOOL_PREFIX,
)
from ._noop import NoOpSpan, NoOpTracer, SpanAttributeValue

if TYPE_CHECKING:
    from contextlib import AbstractContextManager

T = TypeVar("T")

# === 核心函数 ===


def get_tracer() -> NoOpTracer:
    return NoOpTracer()


def get_meter() -> None:
    pass


def is_initialized() -> bool:
    return False


def setup_observability(**kwargs) -> tuple[NoOpTracer, None]:
    return NoOpTracer(), None


def shutdown_observability() -> None:
    pass

# === 错误处理 ===


def classify_error(error: Exception) -> str:
    """错误分类"""
    error_str = str(error).lower()
    if "rate limit" in error_str or "429" in error_str:
        return "ratelimit"
    if "timeout" in error_str:
        return "timeout"
    if "connection" in error_str or "network" in error_str:
        return "connection"
    return "api_error"


def record_llm_span_error(span: NoOpSpan, error: Exception) -> str:
    return classify_error(error)


def record_llm_success(provider: str, model: str, input_tokens: int, output_tokens: int, duration_ms: float) -> None:
    pass


def record_llm_error(provider: str, model: str, duration_ms: float, error_type: str) -> None:
    pass


def add_fallback_event(span: NoOpSpan, from_provider: str, to_provider: str, reason: str, attempt: int) -> None:
    pass

# === Span 属性设置 ===


def set_llm_span_attributes(span: NoOpSpan, model: str, provider: str, streaming: bool = False,
                             input_tokens: int | None = None, output_tokens: int | None = None) -> None:
    pass


def set_tool_span_attributes(span: NoOpSpan, tool_name: str, file_path: str | None = None,
                             duration_ms: float | None = None) -> None:
    pass


def set_subagent_span_attributes(span: NoOpSpan, subagent_type: str, task_id: str, status: str | None = None) -> None:
    pass

# === Span 创建 ===


def start_span(name: str, attributes: dict[str, SpanAttributeValue] | None = None) -> NoOpSpan:
    return NoOpSpan()


def start_as_current_span(name: str, attributes: dict[str, SpanAttributeValue] | None = None) -> "AbstractContextManager[NoOpSpan]":
    class NoOpContextManager:
        def __enter__(self) -> NoOpSpan:
            return NoOpSpan()
        def __exit__(self, *args) -> None:
            pass
    return NoOpContextManager()

# === 异步与装饰器 ===


def create_task_with_context(coro: Coroutine[Any, Any, T], ctx: object = None) -> asyncio.Task[T]:
    return asyncio.create_task(coro)


def traced(name: str | None = None, attributes: dict[str, SpanAttributeValue] | None = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    return lambda f: f


__all__ = [
    "SPAN_LLM_FALLBACK",
    "SPAN_LLM_REQUEST",
    "SPAN_SESSION",
    "SPAN_SUBAGENT_EXECUTE",
    "SPAN_TOOL_PREFIX",
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