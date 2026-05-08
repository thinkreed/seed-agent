"""
OpenTelemetry Metrics Instruments 底层管理

包含:
- 全局 instruments 定义
- 延迟初始化逻辑
- Getter 函数
"""

import threading
from typing import TYPE_CHECKING

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