"""
OpenTelemetry SDK 初始化模块

负责:
1. TracerProvider 初始化
2. MeterProvider 初始化
3. OTLP HTTP Exporter 配置
4. Resource 配置 (服务名、版本等)

配置说明:
- 使用 OTLP HTTP 协议（比 gRPC 更稳定）
- 使用 BatchSpanProcessor 批量发送 traces（生产环境推荐）
- 使用 PeriodicExportingMetricReader 定期发送 metrics
- 批量参数: 队列大小 2048, 每 5秒发送, 每批最大 512 spans
"""

import logging
import os
import threading

# 类型注解使用内置类型
from opentelemetry import metrics, trace

# 使用 OTLP HTTP exporter（更稳定）
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

logger = logging.getLogger(__name__)

# 全局状态（线程锁保护）
_tracer: trace.Tracer | None = None
_meter: metrics.Meter | None = None
_trace_provider: TracerProvider | None = None
_meter_provider: MeterProvider | None = None
_initialized: bool = False
_init_lock: threading.Lock = threading.Lock()


def setup_observability(
    service_name: str = "seed-agent",
    otlp_endpoint: str | None = None,
    enabled: bool = True,
) -> tuple[trace.Tracer | None, metrics.Meter | None]:
    """
    初始化 OpenTelemetry SDK

    Args:
        service_name: 服务名称
        otlp_endpoint: OTLP HTTP endpoint (默认 http://localhost:4318)
        enabled: 是否启用可观测性 (默认 True)

    Returns:
        (tracer, meter): OpenTelemetry Tracer 和 Meter 实例
    """
    global _tracer, _meter, _trace_provider, _meter_provider, _initialized

    # 双重检查锁定模式：避免每次调用都获取锁
    if _initialized:
        logger.warning("Observability already initialized, returning existing instances")
        return _tracer, _meter

    with _init_lock:
        # 再次检查，防止锁等待期间其他线程已初始化
        if _initialized:
            return _tracer, _meter

        if not enabled:
            _tracer = trace.NoOpTracer()
            _meter = metrics.NoOpMeter("seed-agent")
            _initialized = True
            logger.info("Observability disabled, using noop providers")
            return _tracer, _meter

        # OTLP HTTP endpoint
        endpoint = otlp_endpoint or os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "http://localhost:4318"
        )
        # 确保 endpoint 不为 None
        if endpoint is None:
            endpoint = "http://localhost:4318"

        # 确保路径正确
        trace_endpoint = endpoint.rstrip("/") + "/v1/traces"
        metric_endpoint = endpoint.rstrip("/") + "/v1/metrics"

        # Resource 配置
        resource = Resource.create({
            SERVICE_NAME: service_name,
            SERVICE_VERSION: "1.0.0",
            "deployment.environment": os.getenv("DEPLOYMENT_ENV", "local"),
        })

        # Traces - 使用 BatchSpanProcessor 批量发送（生产环境推荐）
        _trace_provider = TracerProvider(resource=resource)
        _trace_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=trace_endpoint),
                max_queue_size=2048,           # 最大队列大小
                schedule_delay_millis=5000,    # 5秒批量发送一次
                export_timeout_millis=30000,   # 导出超时 30秒
                max_export_batch_size=512,     # 每批最大 512 个 span
            )
        )
        trace.set_tracer_provider(_trace_provider)

        # Metrics - 使用 PeriodicExportingMetricReader 定期发送
        metric_reader = PeriodicExportingMetricReader(
            exporter=OTLPMetricExporter(endpoint=metric_endpoint),
            export_interval_millis=15000,  # 每 15 秒发送一次
        )
        _meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
        )
        metrics.set_meter_provider(_meter_provider)

        _tracer = trace.get_tracer(service_name)
        _meter = metrics.get_meter(service_name)
        _initialized = True

        logger.info(
            f"Observability initialized: service={service_name}, "
            f"trace_endpoint={trace_endpoint}, metric_endpoint={metric_endpoint}"
        )
        return _tracer, _meter


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
    """
    关闭可观测性系统，强制 flush 所有 pending spans

    应在程序退出前调用，确保所有 traces 发送到 collector
    """
    global _tracer, _meter, _initialized

    # 双重检查锁定模式
    if not _initialized:
        return

    with _init_lock:
        if not _initialized:
            return

        # 获取 TracerProvider 并强制 shutdown
        provider = trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
            logger.info("Observability shutdown complete")

        _tracer = None
        _meter = None
        _initialized = False
