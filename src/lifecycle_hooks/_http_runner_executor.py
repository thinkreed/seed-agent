"""HTTP 钩子执行器核心逻辑

提取自 _http_runner_async.py 的执行逻辑
"""

import asyncio
import json
import logging

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    aiohttp = None  # type: ignore

from ._http_runner_types import HttpHookConfig, HttpHookResult

logger = logging.getLogger("seed_agent")

# 大小限制常量
MAX_REQUEST_SIZE = 1024 * 1024  # 1 MB
MAX_RESPONSE_SIZE = 1024 * 1024  # 1 MB


def prepare_request(
    config: HttpHookConfig | None,
    url: str | None,
    method: str | None,
    headers: dict[str, str] | None,
    body: dict[str, object] | str | None,
    timeout: float | None,
    default_timeout: float,
) -> tuple[str, str, dict[str, str], str | None, float, int, float] | HttpHookResult:
    """准备请求参数，返回 (url, method, headers, body, timeout, retries, retry_delay) 或错误"""
    if config:
        target_url = config.url
        http_method = config.method.upper()
        req_headers = config.headers or {}
        req_body = config.body
        t = config.timeout
        retries = config.retry_count
        retry_delay = config.retry_delay
    else:
        target_url = url or ""
        http_method = (method or "POST").upper()
        req_headers = headers or {}
        req_body = body
        t = timeout or default_timeout
        retries = 0
        retry_delay = 1.0

    if not target_url:
        return HttpHookResult(success=False, error="Empty URL")

    # 处理请求体
    json_body: str | None = None
    if req_body:
        json_body = json.dumps(req_body) if isinstance(req_body, dict) else str(req_body)
        if len(json_body) > MAX_REQUEST_SIZE:
            return HttpHookResult(success=False, error=f"Request body too large: {len(json_body)} bytes")

    # 设置默认 Content-Type
    final_headers = req_headers.copy()
    if json_body and "Content-Type" not in final_headers:
        final_headers["Content-Type"] = "application/json"

    return (target_url, http_method, final_headers, json_body, t, retries, retry_delay)


async def execute_request(
    url: str,
    method: str,
    headers: dict[str, str],
    body: str | None,
    timeout: float,
    retries: int,
    retry_delay: float,
) -> HttpHookResult:
    """执行 HTTP 请求（带重试）"""
    if not HAS_AIOHTTP:
        logger.warning("aiohttp not available, HTTP hooks disabled")
        return HttpHookResult(success=False, error="aiohttp not installed")

    start_time = asyncio.get_event_loop().time()
    attempts = 0
    last_error: str | None = None

    while attempts <= retries:
        attempts += 1
        try:
            timeout_obj = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                async with session.request(method, url, headers=headers, data=body) as response:
                    response_text = await response.text()
                    if len(response_text) > MAX_RESPONSE_SIZE:
                        response_text = response_text[:MAX_RESPONSE_SIZE]

                    duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                    if 200 <= response.status < 300:
                        logger.debug(f"HTTP hook success: {url[:50]}...")
                        return HttpHookResult(
                            success=True,
                            status_code=response.status,
                            response_body=response_text,
                            duration_ms=duration_ms,
                            attempts=attempts,
                        )
                    last_error = f"HTTP {response.status}: {response_text[:200]}"
                    if attempts <= retries:
                        await asyncio.sleep(retry_delay)

        except TimeoutError:
            last_error = f"Timeout after {timeout}s"
            if attempts <= retries:
                await asyncio.sleep(retry_delay)
        except aiohttp.ClientError as e:
            last_error = f"HTTP client error: {type(e).__name__}: {str(e)[:100]}"
            if attempts <= retries:
                await asyncio.sleep(retry_delay)
        except Exception as e:
            last_error = f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"
            break

    duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
    logger.warning(f"HTTP hook failed: {url[:50]}..., error={last_error}")
    return HttpHookResult(
        success=False,
        status_code=0,
        duration_ms=duration_ms,
        error=last_error,
        attempts=attempts,
    )


__all__ = ["prepare_request", "execute_request", "MAX_REQUEST_SIZE", "MAX_RESPONSE_SIZE"]