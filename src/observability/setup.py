"""
OpenTelemetry SDK 初始化模块

负责:
1. TracerProvider 初始化
2. OTLP HTTP Exporter 配置
3. Resource 配置 (服务名、版本等)

注意：使用 OTLP HTTP 协议，因为 Jaeger 的 OTLP gRPC 在 Windows Docker 环境下有兼容性问题
"""

import os
import logging
from typing import Optional

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION

# 使用 OTLP HTTP exporter（更稳定）
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

logger = logging.getLogger(__name__)

# 全局状态
_tracer: Optional[trace.Tracer] = None
_meter: Optional[metrics.Meter] = None
_initialized: bool = False


def setup_observability(
    service_name: str = "seed-agent",
    otlp_endpoint: Optional[str] = None,
    enabled: bool = True,
) -> tuple[trace.Tracer, metrics.Meter]:
    """
    初始化 OpenTelemetry SDK

    Args:
        service_name: 服务名称
        otlp_endpoint: OTLP HTTP endpoint (默认 http://localhost:4318)
        enabled: 是否启用可观测性 (默认 True)

    Returns:
        (tracer, meter): OpenTelemetry Tracer 和 Meter 实例
    """
    global _tracer, _meter, _initialized

    if _initialized:
        logger.warning("Observability already initialized, returning existing instances")
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
    
    # 确保路径正确
    if not endpoint.endswith("/v1/traces"):
        endpoint = endpoint.rstrip("/") + "/v1/traces"

    # Resource 配置
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: "1.0.0",
        "deployment.environment": os.getenv("DEPLOYMENT_ENV", "local"),
    })

    # Traces - 使用 SimpleSpanProcessor 立即发送
    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(
        SimpleSpanProcessor(
            OTLPSpanExporter(endpoint=endpoint)
        )
    )
    trace.set_tracer_provider(trace_provider)

    _tracer = trace.get_tracer(service_name)
    _meter = metrics.NoOpMeter("seed-agent")
    _initialized = True

    logger.info(f"Observability initialized: service={service_name}, endpoint={endpoint}")
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