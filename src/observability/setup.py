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
- Endpoint 不可达时自动降级为 noop，避免重复错误日志
"""

import logging
import os
import threading
import urllib.request
import urllib.error

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

# Endpoint 健康检查缓存（避免重复检查）
_endpoint_health_cache: dict[str, bool] = {}
_endpoint_health_cache_lock = threading.Lock()
_ENDPOINT_CHECK_TIMEOUT = 2.0  # 健康检查超时时间（秒）


def _check_endpoint_health(endpoint: str) -> bool:
    """检查 OTLP endpoint 是否可达

    使用简单的 HTTP GET 请求检测 collector 是否运行。
    OpenTelemetry Collector 通常在根路径返回 404 或 200，
    只要能建立连接就认为可达。

    Args:
        endpoint: OTLP HTTP endpoint URL

    Returns:
        True 表示可达，False 表示不可达
    """
    with _endpoint_health_cache_lock:
        if endpoint in _endpoint_health_cache:
            return _endpoint_health_cache[endpoint]

    try:
        # 使用 HEAD 请求（更快）
        url = endpoint.rstrip("/")
        req = urllib.request.Request(url, method="HEAD")
        urllib.request.urlopen(req, timeout=_ENDPOINT_CHECK_TIMEOUT)
        # 任何响应（包括 404）都表示 collector 运行
        with _endpoint_health_cache_lock:
            _endpoint_health_cache[endpoint] = True
        return True
    except urllib.error.URLError:
        # 连接失败（collector 未运行）
        logger.info(f"OTLP endpoint {endpoint} not reachable, using noop providers")
        with _endpoint_health_cache_lock:
            _endpoint_health_cache[endpoint] = False
        return False
    except Exception as e:
        # 其他错误（超时等）
        logger.debug(f"Endpoint health check failed: {e}")
        with _endpoint_health_cache_lock:
            _endpoint_health_cache[endpoint] = False
        return False


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
        logger.warning(
            "Observability already initialized, returning existing instances"
        )
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
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
        )
        # 确保 endpoint 不为 None
        if endpoint is None:
            endpoint = "http://localhost:4318"

        # 检查 endpoint 可达性
        endpoint_reachable = _check_endpoint_health(endpoint)

        if not endpoint_reachable:
            # Endpoint 不可达，使用 noop providers
            _tracer = trace.NoOpTracer()
            _meter = metrics.NoOpMeter(service_name)
            _initialized = True
            logger.info(
                f"OTLP endpoint {endpoint} not available, "
                "observability disabled (no collector running)"
            )
            return _tracer, _meter

        # 确保路径正确
        trace_endpoint = endpoint.rstrip("/") + "/v1/traces"
        metric_endpoint = endpoint.rstrip("/") + "/v1/metrics"

        # Resource 配置
        resource = Resource.create(
            {
                SERVICE_NAME: service_name,
                SERVICE_VERSION: "1.0.0",
                "deployment.environment": os.getenv("DEPLOYMENT_ENV", "local"),
            }
        )

        # Traces - 使用 BatchSpanProcessor 批量发送（生产环境推荐）
        _trace_provider = TracerProvider(resource=resource)
        _trace_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=trace_endpoint),
                max_queue_size=2048,  # 最大队列大小
                schedule_delay_millis=5000,  # 5秒批量发送一次
                export_timeout_millis=30000,  # 导出超时 30秒
                max_export_batch_size=512,  # 每批最大 512 个 span
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
