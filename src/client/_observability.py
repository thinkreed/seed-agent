"""
可观测性集成模块

提供:
- create_llm_span: 创建 OpenTelemetry LLM Span
- record_success_metrics: 记录成功调用的 Metrics
- handle_llm_error: 记录失败调用的 Metrics
"""

from typing import Any

from src.observability import (
    SPAN_LLM_REQUEST,
    StatusCode,
    classify_error,
    get_tracer,
    is_observability_enabled,
    record_llm_error,
    record_llm_span_error,
    record_llm_success,
    set_llm_span_attributes,
)

_OBSERVABILITY_ENABLED = is_observability_enabled()


def create_llm_span(model_id: str, provider: str, streaming: bool = False) -> Any:
    """创建 OpenTelemetry LLM Span

    Args:
        model_id: 模型 ID
        provider: Provider 名称
        streaming: 是否为流式请求

    Returns:
        OpenTelemetry Span 或 None（如果可观测性未启用）
    """
    tracer = get_tracer()
    if tracer and _OBSERVABILITY_ENABLED:
        span = tracer.start_span(SPAN_LLM_REQUEST)
        set_llm_span_attributes(
            span, model=model_id, provider=provider, streaming=streaming
        )
        return span
    return None


def record_success_metrics(
    span: Any,
    provider: str,
    model_id: str,
    usage: dict | None,
    duration_ms: float,
) -> None:
    """记录成功调用的 Metrics 和 Span 属性

    Args:
        span: OpenTelemetry Span
        provider: Provider 名称
        model_id: 模型 ID
        usage: Token 使用情况
        duration_ms: 耗时（毫秒）
    """
    if usage is None:
        usage = {}
    if usage:
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        record_llm_success(
            provider=provider,
            model=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_ms=duration_ms,
        )

        if span:
            span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
            span.set_status(StatusCode.OK)

    if span and provider != model_id.split("/", maxsplit=1)[0]:
        span.set_attribute("seed.provider", provider)


def handle_llm_error(
    span: Any,
    provider: str,
    model_id: str,
    start_time: float,
    e: Exception,
) -> None:
    """记录失败调用的 Metrics 和 Span 错误

    Args:
        span: OpenTelemetry Span
        provider: Provider 名称
        model_id: 模型 ID
        start_time: 开始时间
        e: 异常实例
    """
    from src.client._utils import _calc_duration_ms

    duration_ms = _calc_duration_ms(start_time)
    error_type = classify_error(e)

    record_llm_error(
        provider=provider,
        model=model_id,
        duration_ms=duration_ms,
        error_type=error_type,
    )

    if span:
        record_llm_span_error(span, e)
