"""HTTP 钩子异步执行器

Wiki 知识落地 (Qwen-Code): HTTP Hooks

核心功能：
- 异步 HTTP 请求
- 超时控制
- 重试机制
- 错误处理
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
        body: dict[str, object] | str | None = None,
        timeout: float | None = None,
    ) -> HttpHookResult:
        """执行 HTTP 钩子

        Args:
            config: 钩子配置对象
            url: URL（如果未提供 config）
            method: HTTP 方法
            headers: 请求头
            body: 请求体
            timeout: 超时时间

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

            except TimeoutError:
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

    def get_stats(self) -> dict[str, object]:
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


__all__ = ["HttpHookRunner"]