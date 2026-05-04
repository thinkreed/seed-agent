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

import threading
from typing import TYPE_CHECKING

# 类型注解使用内置类型
from opentelemetry import metrics

from .setup import get_meter

if TYPE_CHECKING:
    from opentelemetry.util.types import Attributes

# Histogram buckets (延迟分布)
DURATION_BUCKETS = [100, 500, 1000, 2000, 5000, 10000]  # ms

# 全局 instruments (延迟初始化)
_tokens_input_counter: metrics.Counter | None = None
_tokens_output_counter: metrics.Counter | None = None
_request_counter: metrics.Counter | None = None
_error_counter: metrics.Counter | None = None
_duration_histogram: metrics.Histogram | None = None

# 线程安全锁（保护初始化）
_init_lock = threading.Lock()
_initialized = False


def _init_instruments() -> None:
    """延迟初始化 Instruments（线程安全，双重检查锁定）"""
    global _tokens_input_counter, _tokens_output_counter
    global _request_counter, _error_counter, _duration_histogram, _initialized

    # 快速检查：已初始化则跳过
    if _initialized:
        return

    # 线程安全初始化
    with _init_lock:
        # 双重检查：防止多线程同时进入锁后重复初始化
        if _initialized:
            return

        meter = get_meter()

        # Token Counters
        _tokens_input_counter = meter.create_counter(
            name="seed.llm.tokens.input",
            description="Total input tokens consumed",
            unit="1",
        )

        _tokens_output_counter = meter.create_counter(
            name="seed.llm.tokens.output",
            description="Total output tokens generated",
            unit="1",
        )

        # Request Counter
        _request_counter = meter.create_counter(
            name="seed.llm.request.count", description="Total LLM requests", unit="1"
        )

        # Error Counter
        _error_counter = meter.create_counter(
            name="seed.llm.error.count", description="LLM errors by type", unit="1"
        )

        # Duration Histogram
        _duration_histogram = meter.create_histogram(
            name="seed.llm.request.duration",
            description="LLM request duration distribution",
            unit="ms",
            explicit_bucket_boundaries_advisory=DURATION_BUCKETS,
        )

        _initialized = True


def get_tokens_input_counter() -> metrics.Counter | None:
    """获取输入 Token Counter"""
    global _tokens_input_counter
    if _tokens_input_counter is None:
        _init_instruments()
    return _tokens_input_counter


def get_tokens_output_counter() -> metrics.Counter | None:
    """获取输出 Token Counter"""
    global _tokens_output_counter
    if _tokens_output_counter is None:
        _init_instruments()
    return _tokens_output_counter


def get_request_counter() -> metrics.Counter | None:
    """获取请求计数 Counter"""
    global _request_counter
    if _request_counter is None:
        _init_instruments()
    return _request_counter


def get_error_counter() -> metrics.Counter | None:
    """获取错误计数 Counter"""
    global _error_counter
    if _error_counter is None:
        _init_instruments()
    return _error_counter


def get_duration_histogram() -> metrics.Histogram | None:
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
