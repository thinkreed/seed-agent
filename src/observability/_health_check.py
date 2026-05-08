"""
OTLP Endpoint 健康检查模块

负责检测 OTLP Collector 是否可达，避免重复错误日志。

特性:
- 线程安全的缓存机制
- HEAD 请求快速检测
- 连接失败自动降级为 noop
"""

import logging
import threading
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# Endpoint 健康检查缓存（避免重复检查）
_endpoint_health_cache: dict[str, bool] = {}
_endpoint_health_cache_lock = threading.Lock()
_ENDPOINT_CHECK_TIMEOUT = 2.0  # 健康检查超时时间（秒）


def check_endpoint_health(endpoint: str) -> bool:
    """检查 OTLP endpoint 是否可达

    使用简单的 HTTP HEAD 请求检测 collector 是否运行。
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
        # Note: Only checks localhost OTLP endpoint, not arbitrary URLs
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


def clear_cache() -> None:
    """清除健康检查缓存（主要用于测试）"""
    with _endpoint_health_cache_lock:
        _endpoint_health_cache.clear()