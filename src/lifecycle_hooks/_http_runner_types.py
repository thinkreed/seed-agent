"""HTTP 钩子类型定义

Wiki 知识落地 (Qwen-Code): HTTP Hooks
"""

from dataclasses import dataclass, field
from typing import Any


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


__all__ = ["HttpHookConfig", "HttpHookResult"]