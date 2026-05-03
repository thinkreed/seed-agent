"""
OpenTelemetry Tracing Helpers

提供:
1. Span 创建和属性设置
2. 错误记录和分类
3. asyncio context 传播
4. 装饰器封装

Span 层级:
- seed.session (Root Span)
- seed.llm.request (LLM 调用)
- seed.llm.fallback (Provider 切换)
- seed.tool.{name} (工具调用)
- seed.subagent.execute (Subagent 执行)
"""

import asyncio
import functools
from typing import Any, Callable, Coroutine, TypeVar

from opentelemetry import context
from opentelemetry.trace import Span, StatusCode

from .setup import get_tracer

# 类型别名，用于 Span 属性值
SpanAttributeValue = str | int | float | bool

T = TypeVar("T")

# Span 名称常量
SPAN_SESSION = "seed.session"
SPAN_LLM_REQUEST = "seed.llm.request"
SPAN_LLM_FALLBACK = "seed.llm.fallback"
SPAN_TOOL_PREFIX = "seed.tool."
SPAN_SUBAGENT_EXECUTE = "seed.subagent.execute"

# 错误类型分类
ERROR_TYPES = {
    "ratelimit": ["rate limit", "429"],
    "timeout": ["timeout", "timed out"],
    "connection": ["connection", "connect", "network"],
    "context_overflow": ["context", "overflow", "too long"],
}


def classify_error(error: Exception) -> str:
    """
    将异常分类为标准错误类型

    Args:
        error: 异常实例

    Returns:
        错误类型字符串:
        - ratelimit: 429 Rate Limit
        - timeout: 请求超时
        - connection: 网络连接错误
        - context_overflow: 上下文窗口溢出
        - api_error: 其他 API 错误
    """
    error_str = str(error).lower()

    for error_type, keywords in ERROR_TYPES.items():
        if any(kw in error_str for kw in keywords):
            return error_type

    return "api_error"


def record_llm_span_error(span: Span, error: Exception) -> str:
    """
    在 Span 上记录 LLM 错误

    Args:
        span: OpenTelemetry Span
        error: 异常实例

    Returns:
        错误类型字符串
    """
    error_type = classify_error(error)
    error_msg = str(error)

    # 截断错误消息至 500 字符
    truncated_msg = error_msg[:500] if len(error_msg) > 500 else error_msg

    span.record_exception(error)
    span.set_attribute("seed.error.type", error_type)
    span.set_attribute("seed.error.message", truncated_msg)
    span.set_status(StatusCode.ERROR, error_msg[:200])

    return error_type


def create_task_with_context(coro: Coroutine[Any, Any, T], ctx: context.Context | None = None) -> asyncio.Task[T]:
    """
    创建继承 OTel context 的 asyncio task

    解决 asyncio.create_task() 默认不继承 context 的问题

    Args:
        coro: 协程对象
        ctx: Context (默认使用当前 context)

    Returns:
        asyncio.Task
    """
    if ctx is None:
        ctx = context.get_current()

    # 使用 context.attach/detach 正确传播 context
    # 这是 OpenTelemetry 推荐的方式
    token = context.attach(ctx)
    try:
        task = asyncio.create_task(coro)
        # 任务创建后，context 已被继承，可以安全 detach
        context.detach(token)
        return task
    except Exception:
        # 异常时也要 detach
        context.detach(token)
        raise


def start_span(
    name: str,
    attributes: dict[str, SpanAttributeValue] | None = None,
) -> Span:
    """
    启动一个新 Span

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
    """
    启动一个作为当前 Span 的新 Span

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
    """
    装饰器：自动创建 Span 包装函数

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
        async def async_wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)

                try:
                    result = await func(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(StatusCode.ERROR, str(e)[:200])
                    raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
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


def add_fallback_event(
    span: Span,
    from_provider: str,
    to_provider: str,
    reason: str,
    attempt: int,
):
    """
    在 Span 上添加 Fallback 事件

    Args:
        span: 当前 Span
        from_provider: 原 Provider
        to_provider: 新 Provider
        reason: 切换原因 (error/ratelimit/timeout)
        attempt: 当前尝试次数
    """
    span.add_event(
        "seed.llm.fallback",
        {
            "seed.fallback.from": from_provider,
            "seed.fallback.to": to_provider,
            "seed.fallback.reason": reason,
            "seed.fallback.attempt": attempt,
        }
    )


def set_llm_span_attributes(
    span: Span,
    model: str,
    provider: str,
    streaming: bool = False,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
):
    """
    设置 LLM Span 的标准属性

    按照 OTel Semantic Conventions 设置属性

    Args:
        span: Span 实例
        model: 模型 ID
        provider: Provider 名称
        streaming: 是否流式响应
        input_tokens: 输入 Token 数
        output_tokens: 输出 Token 数
    """
    span.set_attribute("gen_ai.system", "openai")
    span.set_attribute("gen_ai.request.model", model)
    span.set_attribute("seed.provider", provider)
    span.set_attribute("seed.streaming", streaming)

    if input_tokens is not None:
        span.set_attribute("gen_ai.usage.input_tokens", input_tokens)

    if output_tokens is not None:
        span.set_attribute("gen_ai.usage.output_tokens", output_tokens)


def set_tool_span_attributes(
    span: Span,
    tool_name: str,
    file_path: str | None = None,
    duration_ms: float | None = None,
):
    """
    设置工具调用 Span 的属性

    Args:
        span: Span 实例
        tool_name: 工具名称
        file_path: 文件路径 (文件操作工具)
        duration_ms: 执行耗时
    """
    span.set_attribute("code.function.name", tool_name)

    if file_path:
        # 脱敏：仅存相对路径
        if len(file_path) > 200:
            file_path = file_path[:200]
        span.set_attribute("seed.tool.file_path", file_path)

    if duration_ms is not None:
        span.set_attribute("seed.tool.duration_ms", duration_ms)


def set_subagent_span_attributes(
    span: Span,
    subagent_type: str,
    task_id: str,
    status: str | None = None,
):
    """
    设置 Subagent Span 的属性

    Args:
        span: Span 实例
        subagent_type: Subagent 类型 (EXPLORE/REVIEW/IMPLEMENT/PLAN)
        task_id: 任务 ID
        status: 执行状态 (completed/failed/timeout)
    """
    span.set_attribute("seed.subagent.type", subagent_type)
    span.set_attribute("seed.subagent.task_id", task_id)

    if status:
        span.set_attribute("seed.subagent.status", status)
