"""
OpenTelemetry Metrics Instruments 定义

Metrics 类型:
- seed.llm.tokens.input: 输入 Token 累计
- seed.llm.tokens.output: 输出 Token 累计
- seed.llm.request.duration: LLM 请求耗时分布
- seed.llm.request.count: LLM 请求计数
- seed.llm.error.count: LLM 错误分类统计

使用方式:
    from observability.metrics import record_llm_success, record_llm_error
"""

from typing import TYPE_CHECKING

from ._metrics_instruments import (
    get_duration_histogram,
    get_error_counter,
    get_request_counter,
    get_tokens_input_counter,
    get_tokens_output_counter,
)

if TYPE_CHECKING:
    from opentelemetry.util.types import Attributes


def record_llm_success(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    duration_ms: float,
):
    """
    记录成功的 LLM 请求

    Args:
        provider: Provider 名称
        model: 模型 ID
        input_tokens: 输入 Token 数
        output_tokens: 输出 Token 数
        duration_ms: 请求耗时 (毫秒)
    """
    attrs: Attributes = {
        "provider": provider,
        "model": model,
        "status": "success",
    }

    counter_input = get_tokens_input_counter()
    counter_output = get_tokens_output_counter()
    counter_req = get_request_counter()
    histogram = get_duration_histogram()

    if counter_input:
        counter_input.add(input_tokens, attrs)
    if counter_output:
        counter_output.add(output_tokens, attrs)
    if counter_req:
        counter_req.add(1, attrs)
    if histogram:
        histogram.record(duration_ms, attrs)


def record_llm_error(
    provider: str,
    model: str,
    duration_ms: float,
    error_type: str,
):
    """
    记录失败的 LLM 请求

    Args:
        provider: Provider 名称
        model: 模型 ID
        duration_ms: 请求耗时 (毫秒)
        error_type: 错误类型 (connection/ratelimit/timeout/api_error/context_overflow)
    """
    attrs: Attributes = {
        "provider": provider,
        "model": model,
        "status": "error",
    }

    counter_req = get_request_counter()
    histogram = get_duration_histogram()
    counter_err = get_error_counter()

    if counter_req:
        counter_req.add(1, attrs)
    if histogram:
        histogram.record(duration_ms, attrs)

    # 错误类型计数
    error_attrs: Attributes = {
        "provider": provider,
        "model": model,
        "error_type": error_type,
    }
    if counter_err:
        counter_err.add(1, error_attrs)