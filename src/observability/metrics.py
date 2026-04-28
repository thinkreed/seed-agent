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

from typing import Dict, Optional
from opentelemetry import metrics
from opentelemetry.util.types import Attributes

from observability.setup import get_meter

# Histogram buckets (延迟分布)
DURATION_BUCKETS = [100, 500, 1000, 2000, 5000, 10000]  # ms

# 全局 instruments (延迟初始化)
_tokens_input_counter: Optional[metrics.Counter] = None
_tokens_output_counter: Optional[metrics.Counter] = None
_request_counter: Optional[metrics.Counter] = None
_error_counter: Optional[metrics.Counter] = None
_duration_histogram: Optional[metrics.Histogram] = None


def _init_instruments():
    """延迟初始化 Instruments"""
    global _tokens_input_counter, _tokens_output_counter
    global _request_counter, _error_counter, _duration_histogram

    meter = get_meter()

    # Token Counters
    _tokens_input_counter = meter.create_counter(
        name="seed.llm.tokens.input",
        description="Total input tokens consumed",
        unit="1"
    )

    _tokens_output_counter = meter.create_counter(
        name="seed.llm.tokens.output",
        description="Total output tokens generated",
        unit="1"
    )

    # Request Counter
    _request_counter = meter.create_counter(
        name="seed.llm.request.count",
        description="Total LLM requests",
        unit="1"
    )

    # Error Counter
    _error_counter = meter.create_counter(
        name="seed.llm.error.count",
        description="LLM errors by type",
        unit="1"
    )

    # Duration Histogram
    _duration_histogram = meter.create_histogram(
        name="seed.llm.request.duration",
        description="LLM request duration distribution",
        unit="ms",
        explicit_bucket_boundaries_advisory=DURATION_BUCKETS
    )


def get_tokens_input_counter() -> metrics.Counter:
    """获取输入 Token Counter"""
    global _tokens_input_counter
    if _tokens_input_counter is None:
        _init_instruments()
    return _tokens_input_counter


def get_tokens_output_counter() -> metrics.Counter:
    """获取输出 Token Counter"""
    global _tokens_output_counter
    if _tokens_output_counter is None:
        _init_instruments()
    return _tokens_output_counter


def get_request_counter() -> metrics.Counter:
    """获取请求计数 Counter"""
    global _request_counter
    if _request_counter is None:
        _init_instruments()
    return _request_counter


def get_error_counter() -> metrics.Counter:
    """获取错误计数 Counter"""
    global _error_counter
    if _error_counter is None:
        _init_instruments()
    return _error_counter


def get_duration_histogram() -> metrics.Histogram:
    """获取延迟 Histogram"""
    global _duration_histogram
    if _duration_histogram is None:
        _init_instruments()
    return _duration_histogram


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

    get_tokens_input_counter().add(input_tokens, attrs)
    get_tokens_output_counter().add(output_tokens, attrs)
    get_request_counter().add(1, attrs)
    get_duration_histogram().record(duration_ms, attrs)


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

    get_request_counter().add(1, attrs)
    get_duration_histogram().record(duration_ms, attrs)

    # 错误类型计数
    error_attrs: Attributes = {
        "provider": provider,
        "model": model,
        "error_type": error_type,
    }
    get_error_counter().add(1, error_attrs)