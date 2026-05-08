"""
Observability 全局状态管理

负责管理 Tracer 和 Meter 的全局实例，线程安全访问。
"""

import logging
import threading

from opentelemetry import metrics, trace

logger = logging.getLogger(__name__)

# 全局状态（线程锁保护）
_tracer: trace.Tracer | None = None
_meter: metrics.Meter | None = None
_trace_provider: trace.TracerProvider | None = None
_meter_provider: metrics.MeterProvider | None = None
_initialized: bool = False
_init_lock: threading.Lock = threading.Lock()


def get_tracer() -> trace.Tracer:
    """获取全局 Tracer"""
    global _tracer
    if _tracer is None:
        return trace.NoOpTracer()
    return _tracer


def get_meter() -> metrics.Meter:
    """获取全局 Meter"""
    global _meter
    if _meter is None:
        return metrics.NoOpMeter("seed-agent")
    return _meter


def is_initialized() -> bool:
    """检查是否已初始化"""
    return _initialized


def shutdown_observability() -> None:
    """关闭可观测性系统，强制 flush 所有 pending spans

    应在程序退出前调用，确保所有 traces 发送到 collector
    """
    global _tracer, _meter, _initialized

    if not _initialized:
        return

    with _init_lock:
        if not _initialized:
            return

        provider = trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
            logger.info("Observability shutdown complete")

        _tracer = None
        _meter = None
        _initialized = False


def reset_state() -> None:
    """重置全局状态（主要用于测试）"""
    global _tracer, _meter, _trace_provider, _meter_provider, _initialized
    _tracer = None
    _meter = None
    _trace_provider = None
    _meter_provider = None
    _initialized = False