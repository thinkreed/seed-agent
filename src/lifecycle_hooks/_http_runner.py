"""HTTP 钩子执行器 (Wiki 知识落地 - Qwen-Code)

基于 Qwen-Code HTTP Hooks 设计：
- 在生命周期节点发送 HTTP 请求
- 支持多种请求方法 (GET/POST/PUT/DELETE)
- 支持自定义 headers 和 body
- 超时控制和错误处理

使用场景：
- 触发外部 Webhook
- 调用监控系统 API
- 发送通知到 Slack/Discord
- 记录到外部审计系统

Example:
    runner = HttpHookRunner()

    result = await runner.execute(
        url="https://hooks.slack.com/services/...",
        method="POST",
        headers={"Content-Type": "application/json"},
        body={"text": "Task completed"},
        timeout=10
    )
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    aiohttp = None  # type: ignore

logger = logging.getLogger("seed_agent")


@dataclass
class HttpHookConfig:
    """HTTP 钩子配置

    Attributes:
        url: 目标 URL
        method: HTTP 方法 (GET/POST/PUT/DELETE)
        headers: 请求头
        body: 请求体（字典或字符串）
        timeout: 超时时间（秒）
        retry_count: 重试次数
        retry_delay: 重试延迟（秒）
    """

    url: str
    method: str = "POST"
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] | str | None = None
    timeout: float = 10.0
    retry_count: int = 0
    retry_delay: float = 1.0


@dataclass
class HttpHookResult:
    """HTTP 钩子执行结果

    Attributes:
        success: 是否成功
        status_code: HTTP 状态码
        response_body: 响应体
        duration_ms: 执行时长（毫秒）
        error: 错误信息（如果有）
        attempts: 尝试次数
    """

    success: bool
    status_code: int = 0
    response_body: str = ""
    duration_ms: float = 0.0
    error: str | None = None
    attempts: int = 1

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "status_code": self.status_code,
            "response_body": self.response_body[:1000] if self.response_body else "",
            "duration_ms": self.duration_ms,
            "error": self.error,
            "attempts": self.attempts,
        }


class HttpHookRunner:
    """HTTP 钩子执行器

    Wiki 知识落地 (Qwen-Code HTTP Hooks):
    - 异步 HTTP 请求
    - 超时控制
    - 重试机制
    - 错误处理（失败不中断主流程）

    安全特性：
    - URL 白名单检查（可选）
    - 请求大小限制
    - 响应大小限制
    """

    # 默认 URL 白名单（可选启用）
    DEFAULT_ALLOWED_DOMAINS = [
        "hooks.slack.com",
        "discord.com",
        "api.github.com",
        "grafana.internal",
        "localhost",
        "127.0.0.1",
    ]

    # 请求/响应大小限制
    MAX_REQUEST_SIZE = 1024 * 1024  # 1 MB
    MAX_RESPONSE_SIZE = 1024 * 1024  # 1 MB

    def __init__(
        self,
        allowed_domains: list[str] | None = None,
        default_timeout: float = 10.0,
        enable_whitelist: bool = False,
    ):
        """初始化 HTTP 钩子执行器

        Args:
            allowed_domains: 允许的域名白名单
            default_timeout: 默认超时时间
            enable_whitelist: 是否启用白名单检查
        """
        self._allowed_domains = allowed_domains or self.DEFAULT_ALLOWED_DOMAINS
        self._default_timeout = default_timeout
        self._enable_whitelist = enable_whitelist

        # 统计
        self._total_executions = 0
        self._successful_executions = 0
        self._failed_executions = 0

    def _check_url_allowed(self, url: str) -> bool:
        """检查 URL 是否在白名单中"""
        if not self._enable_whitelist:
            return True

        # 提取域名
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.split(":")[0]  # 移除端口
            return any(d in domain for d in self._allowed_domains)
        except Exception:
            return False

    async def execute(
        self,
        config: HttpHookConfig | None = None,
        url: str | None = None,
        method: str | None = None,
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | str | None = None,
        timeout: float | None = None,
    ) -> HttpHookResult:
        """执行 HTTP 钩子

        Args:
            config: 钩子配置对象
            url: URL（如果未提供 config）
            method: HTTP 方法（如果未提供 config）
            headers: 请求头（如果未提供 config）
            body: 请求体（如果未提供 config）
            timeout: 超时时间（如果未提供 config）

        Returns:
            HttpHookResult 执行结果
        """
        # 参数处理
        if config:
            target_url = config.url
            http_method = config.method.upper()
            req_headers = config.headers
            req_body = config.body
            t = config.timeout
            retries = config.retry_count
            retry_delay = config.retry_delay
        else:
            target_url = url or ""
            http_method = (method or "POST").upper()
            req_headers = headers or {}
            req_body = body
            t = timeout or self._default_timeout
            retries = 0
            retry_delay = 1.0

        if not target_url:
            return HttpHookResult(success=False, error="Empty URL")

        # 白名单检查
        if not self._check_url_allowed(target_url):
            return HttpHookResult(
                success=False,
                error=f"URL not allowed: {target_url}",
            )

        # 检查 aiohttp 是否可用
        if not HAS_AIOHTTP:
            logger.warning("aiohttp not available, HTTP hooks disabled")
            return HttpHookResult(
                success=False,
                error="aiohttp not installed",
            )

        self._total_executions += 1
        start_time = asyncio.get_event_loop().time()

        # 处理请求体
        json_body: str | None = None
        if req_body:
            if isinstance(req_body, dict):
                json_body = json.dumps(req_body)
            else:
                json_body = str(req_body)

            # 检查大小
            if len(json_body) > self.MAX_REQUEST_SIZE:
                return HttpHookResult(
                    success=False,
                    error=f"Request body too large: {len(json_body)} bytes",
                )

        # 设置默认 headers
        final_headers = req_headers.copy()
        if json_body and "Content-Type" not in final_headers:
            final_headers["Content-Type"] = "application/json"

        # 执行请求（带重试）
        attempts = 0
        last_error: str | None = None

        while attempts <= retries:
            attempts += 1
            try:
                timeout_obj = aiohttp.ClientTimeout(total=t)

                async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                    async with session.request(
                        http_method,
                        target_url,
                        headers=final_headers,
                        data=json_body,
                    ) as response:
                        response_text = await response.text()

                        # 检查响应大小
                        if len(response_text) > self.MAX_RESPONSE_SIZE:
                            response_text = response_text[:self.MAX_RESPONSE_SIZE]

                        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                        # 成功状态码：2xx
                        if 200 <= response.status < 300:
                            self._successful_executions += 1
                            logger.debug(f"HTTP hook success: {target_url[:50]}...")
                            return HttpHookResult(
                                success=True,
                                status_code=response.status,
                                response_body=response_text,
                                duration_ms=duration_ms,
                                attempts=attempts,
                            )
                        else:
                            last_error = f"HTTP {response.status}: {response_text[:200]}"
                            if attempts <= retries:
                                await asyncio.sleep(retry_delay)
                                continue

            except asyncio.TimeoutError:
                last_error = f"Timeout after {t}s"
                if attempts <= retries:
                    await asyncio.sleep(retry_delay)
                    continue

            except aiohttp.ClientError as e:
                last_error = f"HTTP client error: {type(e).__name__}: {str(e)[:100]}"
                if attempts <= retries:
                    await asyncio.sleep(retry_delay)
                    continue

            except Exception as e:
                last_error = f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"
                break

        # 所有尝试失败
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        self._failed_executions += 1
        logger.warning(f"HTTP hook failed: {target_url[:50]}..., error={last_error}")

        return HttpHookResult(
            success=False,
            status_code=0,
            duration_ms=duration_ms,
            error=last_error,
            attempts=attempts,
        )

    def get_stats(self) -> dict[str, Any]:
        """获取执行统计"""
        return {
            "total_executions": self._total_executions,
            "successful_executions": self._successful_executions,
            "failed_executions": self._failed_executions,
            "success_rate": (
                self._successful_executions / self._total_executions
                if self._total_executions > 0
                else 0.0
            ),
        }


# 同步版本（用于非异步环境）
def execute_http_hook_sync(
    url: str,
    method: str = "POST",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | str | None = None,
    timeout: float = 10.0,
) -> HttpHookResult:
    """同步执行 HTTP 钩子（用于非异步环境）"""
    import urllib.request
    import urllib.error

    start_time = asyncio.get_event_loop().time()

    try:
        req_body: bytes | None = None
        if body:
            if isinstance(body, dict):
                req_body = json.dumps(body).encode("utf-8")
            else:
                req_body = str(body).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=req_body,
            headers=headers or {},
            method=method.upper(),
        )

        if req_body and "Content-Type" not in (headers or {}):
            req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=timeout) as response:
            response_text = response.read().decode("utf-8", errors="replace")
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000

            return HttpHookResult(
                success=True,
                status_code=response.status,
                response_body=response_text[:HttpHookRunner.MAX_RESPONSE_SIZE],
                duration_ms=duration_ms,
            )

    except urllib.error.HTTPError as e:
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        return HttpHookResult(
            success=False,
            status_code=e.code,
            duration_ms=duration_ms,
            error=f"HTTP {e.code}: {str(e)[:100]}",
        )

    except urllib.error.URLError as e:
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        return HttpHookResult(
            success=False,
            duration_ms=duration_ms,
            error=f"URL error: {str(e)[:100]}",
        )

    except Exception as e:
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        return HttpHookResult(
            success=False,
            duration_ms=duration_ms,
            error=f"Unexpected: {type(e).__name__}: {str(e)[:100]}",
        )


__all__ = [
    "HttpHookConfig",
    "HttpHookResult",
    "HttpHookRunner",
    "execute_http_hook_sync",
]