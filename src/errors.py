"""
统一错误处理模块

提供:
1. 错误分类（统一错误类型识别）
2. 错误严重程度（用于日志级别决策）
3. 标准化日志格式
4. 异常包装器

使用方式:
    from src.errors import classify_error, ErrorSeverity, log_error

    error_type, severity = classify_error(e)
    log_error(logger, e, context="LLM request")
"""

from typing import Any

from ._error_logging import format_error_log, get_log_level, log_error
from ._error_types import ErrorSeverity, ErrorType, classify_error


class SeedAgentError(Exception):
    """Seed-Agent 基础异常类"""

    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.INTERNAL,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: str | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.severity = severity
        self.context = context

    def __str__(self) -> str:
        return format_error_log(self, self.context)


class RateLimitError(SeedAgentError):
    """限流错误"""

    def __init__(self, message: str = "Rate limit exceeded", **kwargs: Any) -> None:
        super().__init__(message, ErrorType.RATELIMIT, ErrorSeverity.MEDIUM, **kwargs)


class SeedTimeoutError(SeedAgentError):
    """超时错误（避免与内置 TimeoutError 冲突）"""

    def __init__(self, message: str = "Operation timed out", **kwargs: Any) -> None:
        super().__init__(message, ErrorType.TIMEOUT, ErrorSeverity.MEDIUM, **kwargs)


class SeedConnectionError(SeedAgentError):
    """连接错误（避免与内置 ConnectionError 冲突）"""

    def __init__(self, message: str = "Connection failed", **kwargs: Any) -> None:
        super().__init__(message, ErrorType.CONNECTION, ErrorSeverity.MEDIUM, **kwargs)


class ConfigurationError(SeedAgentError):
    """配置错误"""

    def __init__(self, message: str = "Configuration error", **kwargs: Any) -> None:
        super().__init__(message, ErrorType.CONFIG, ErrorSeverity.HIGH, **kwargs)


__all__ = [
    "ConfigurationError",
    "ErrorSeverity",
    "ErrorType",
    "RateLimitError",
    "SeedAgentError",
    "SeedConnectionError",
    "SeedTimeoutError",
    "classify_error",
    "format_error_log",
    "get_log_level",
    "log_error",
]