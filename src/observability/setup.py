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
- Endpoint 不可达时自动降级为 noop，避免重复错误日志
"""

import logging
import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from ._health_check import check_endpoint_health
from ._state import (
    _init_lock,
    _initialized,
    _meter,
    _meter_provider,
    _tracer,
    _trace_provider,
    get_meter,
    get_tracer,
    is_initialized,
    shutdown_observability,
)

logger = logging.getLogger(__name__)

__all__ = [
    "setup_observability",
    "get_tracer",
    "get_meter",
    "is_initialized",
    "shutdown_observability",
]


def setup_observability(
    service_name: str = "seed-agent",
    otlp_endpoint: str | None = None,
    enabled: bool = True,
) -> tuple[trace.Tracer | None, metrics.Meter | None]:
    """初始化 OpenTelemetry SDK

    Args:
        service_name: 服务名称
        otlp_endpoint: OTLP HTTP endpoint (默认 http://localhost:4318)
        enabled: 是否启用可观测性 (默认 True)

    Returns:
        (tracer, meter): OpenTelemetry Tracer 和 Meter 实例
    """
    global _tracer, _meter, _trace_provider, _meter_provider, _initialized

    if _initialized:
        logger.warning(
            "Observability already initialized, returning existing instances"
        )
        return _tracer, _meter

    with _init_lock:
        if _initialized:
            return _tracer, _meter

        if not enabled:
            _tracer = trace.NoOpTracer()
            _meter = metrics.NoOpMeter("seed-agent")
            _initialized = True
            logger.info("Observability disabled, using noop providers")
            return _tracer, _meter

        endpoint = otlp_endpoint or os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
        )
        if endpoint is None:
            endpoint = "http://localhost:4318"

        if not check_endpoint_health(endpoint):
            _tracer = trace.NoOpTracer()
            _meter = metrics.NoOpMeter(service_name)
            _initialized = True
            logger.info(
                f"OTLP endpoint {endpoint} not available, "
                "observability disabled (no collector running)"
            )
            return _tracer, _meter

        trace_endpoint = endpoint.rstrip("/") + "/v1/traces"
        metric_endpoint = endpoint.rstrip("/") + "/v1/metrics"

        resource = Resource.create(
            {
                SERVICE_NAME: service_name,
                SERVICE_VERSION: "1.0.0",
                "deployment.environment": os.getenv("DEPLOYMENT_ENV", "local"),
            }
        )

        _trace_provider = TracerProvider(resource=resource)
        _trace_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=trace_endpoint),
                max_queue_size=2048,
                schedule_delay_millis=5000,
                export_timeout_millis=30000,
                max_export_batch_size=512,
            )
        )
        trace.set_tracer_provider(_trace_provider)

        metric_reader = PeriodicExportingMetricReader(
            exporter=OTLPMetricExporter(endpoint=metric_endpoint),
            export_interval_millis=15000,
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