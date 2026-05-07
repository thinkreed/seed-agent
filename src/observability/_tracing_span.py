"""
Tracing Span 创建模块

Span 创建和装饰器封装。
"""

import asyncio
import functools
from collections.abc import Callable
from typing import Any, TypeVar

from opentelemetry.trace import Span, StatusCode

from ._tracing_constants import SPAN_TOOL_PREFIX, SpanAttributeValue
from .setup import get_tracer

T = TypeVar("T")


def start_span(
    name: str,
    attributes: dict[str, SpanAttributeValue] | None = None,
) -> Span:
    """启动一个新 Span

    Args:
        name: Span 名称
        attributes: Span 属性

    Returns:
        Span 实例
    """
    tracer = get_tracer()
    span = tracer.start_span(name)

    if attributes:
        for key, value in attributes.items():
            span.set_attribute(key, value)

    return span


def start_as_current_span(
    name: str,
    attributes: dict[str, SpanAttributeValue] | None = None,
):
    """启动一个作为当前 Span 的新 Span

    使用方式:
        with start_as_current_span("seed.tool.file_read", {"seed.tool.file_path": path}) as span:
            # ... 执行操作 ...

    Args:
        name: Span 名称
        attributes: Span 属性

    Returns:
        Span 实例 (context manager)
    """
    tracer = get_tracer()
    return tracer.start_as_current_span(name, attributes=attributes)


def traced(
    name: str | None = None,
    attributes: dict[str, SpanAttributeValue] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """装饰器：自动创建 Span 包装函数

    使用方式:
        @traced("seed.tool.file_read")
        async def file_read(path: str):
            ...

    Args:
        name: Span 名称 (默认使用函数名)
        attributes: Span 属性
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        span_name = name or f"{SPAN_TOOL_PREFIX}{func.__name__}"

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                try:
                    result = await func(*args, **kwargs)  # type: ignore[misc]
                    span.set_status(StatusCode.OK)
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(StatusCode.ERROR, str(e)[:200])
                    raise

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                try:
                    result = func(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(StatusCode.ERROR, str(e)[:200])
                    raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator