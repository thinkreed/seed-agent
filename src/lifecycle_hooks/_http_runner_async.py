"""HTTP 钩子异步执行器

Wiki 知识落地 (Qwen-Code): HTTP Hooks

核心功能：
- 异步 HTTP 请求
- 超时控制
- 重试机制
- 错误处理
"""

import logging
from urllib.parse import urlparse

from ._http_runner_executor import execute_request, prepare_request
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

    DEFAULT_ALLOWED_DOMAINS = [
        "hooks.slack.com",
        "discord.com",
        "api.github.com",
        "grafana.internal",
        "localhost",
        "127.0.0.1",
    ]

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

        try:
            parsed = urlparse(url)
            domain = parsed.netloc.split(":")[0]
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
        """执行 HTTP 钩子"""
        # 准备请求参数
        result = prepare_request(
            config, url, method, headers, body, timeout, self._default_timeout
        )

        # 参数验证失败
        if isinstance(result, HttpHookResult):
            return result

        target_url, http_method, final_headers, json_body, t, retries, retry_delay = result

        # 白名单检查
        if not self._check_url_allowed(target_url):
            return HttpHookResult(success=False, error=f"URL not allowed: {target_url}")

        self._total_executions += 1

        # 执行请求
        exec_result = await execute_request(
            target_url, http_method, final_headers, json_body, t, retries, retry_delay
        )

        # 更新统计
        if exec_result.success:
            self._successful_executions += 1
        else:
            self._failed_executions += 1

        return exec_result

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