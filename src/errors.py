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

import logging
from enum import Enum


class ErrorType(Enum):
    """错误类型枚举"""
    RATELIMIT = "ratelimit"         # API 限流
    TIMEOUT = "timeout"             # 超时
    CONNECTION = "connection"       # 网络/连接错误
    CONTEXT_OVERFLOW = "context"    # 上下文窗口溢出
    PERMISSION = "permission"       # 权限错误
    NOT_FOUND = "not_found"         # 资源不存在
    VALIDATION = "validation"       # 数据验证错误
    CONFIG = "config"               # 配置错误
    API_ERROR = "api_error"         # 其他 API 错误
    INTERNAL = "internal"           # 内部错误


class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"         # 可忽略/自动恢复
    MEDIUM = "medium"   # 需要关注/可能影响功能
    HIGH = "high"       # 严重/需要立即处理
    CRITICAL = "critical"  # 致命/系统不可用


# 错误类型识别规则（按优先级排序）
_ERROR_TYPE_RULES: list[tuple[ErrorType, list[str], ErrorSeverity]] = [
    # 高优先级错误
    (ErrorType.RATELIMIT, ["rate limit", "429", "too many requests"], ErrorSeverity.MEDIUM),
    (ErrorType.TIMEOUT, ["timeout", "timed out", "deadline exceeded"], ErrorSeverity.MEDIUM),
    (ErrorType.CONNECTION, ["connection", "connect", "network", "socket", "dns", "refused"], ErrorSeverity.MEDIUM),
    (ErrorType.PERMISSION, ["permission", "access denied", "unauthorized", "forbidden", "403"], ErrorSeverity.HIGH),
    (ErrorType.NOT_FOUND, ["not found", "404", "does not exist", "no such"], ErrorSeverity.LOW),
    
    # 中优先级错误
    (ErrorType.CONTEXT_OVERFLOW, ["context", "overflow", "too long", "maximum context", "token limit"], ErrorSeverity.HIGH),
    (ErrorType.VALIDATION, ["validation", "invalid", "malformed", "parse error", "json"], ErrorSeverity.MEDIUM),
    (ErrorType.CONFIG, ["config", "configuration", "missing key", "invalid value"], ErrorSeverity.HIGH),
    
    # 低优先级（兜底）
    (ErrorType.API_ERROR, ["api", "server", "500", "502", "503", "internal"], ErrorSeverity.MEDIUM),
]


def classify_error(error: Exception) -> tuple[ErrorType, ErrorSeverity]:
    """
    将异常分类为标准错误类型和严重程度

    Args:
        error: 异常实例

    Returns:
        (ErrorType, ErrorSeverity): 错误类型和严重程度
    """
    error_str = str(error).lower()
    error_class = type(error).__name__.lower()

    # 检查异常类型名称
    for err_type, keywords, severity in _ERROR_TYPE_RULES:
        if err_type.value in error_class:
            return err_type, severity

    # 检查错误消息关键词
    for err_type, keywords, severity in _ERROR_TYPE_RULES:
        if any(kw in error_str for kw in keywords):
            return err_type, severity

    # 默认：内部错误
    return ErrorType.INTERNAL, ErrorSeverity.MEDIUM


def get_log_level(severity: ErrorSeverity) -> int:
    """根据严重程度获取日志级别"""
    level_map = {
        ErrorSeverity.LOW: logging.DEBUG,
        ErrorSeverity.MEDIUM: logging.WARNING,
        ErrorSeverity.HIGH: logging.ERROR,
        ErrorSeverity.CRITICAL: logging.CRITICAL,
    }
    return level_map.get(severity, logging.ERROR)


def format_error_log(
    error: Exception,
    context: str | None = None,
    include_trace: bool = False,
) -> str:
    """
    格式化错误日志消息

    Args:
        error: 异常实例
        context: 错误发生上下文（可选）
        include_trace: 是否包含堆栈信息

    Returns:
        格式化的日志消息
    """
    error_type, severity = classify_error(error)
    error_class = type(error).__name__
    error_msg = str(error)

    # 截断过长的错误消息
    if len(error_msg) > 200:
        error_msg = error_msg[:200] + "..."

    parts = [
        f"[{error_type.value}:{severity.value}]",
        f"{error_class}: {error_msg}",
    ]

    if context:
        parts.insert(1, f"context={context}")

    return " ".join(parts)


def log_error(
    logger: logging.Logger,
    error: Exception,
    context: str | None = None,
    include_trace: bool = False,
) -> None:
    """
    记录错误日志（统一格式）

    Args:
        logger: Logger 实例
        error: 异常实例
        context: 错误发生上下文（可选）
        include_trace: 是否包含堆栈信息
    """
    error_type, severity = classify_error(error)
    log_level = get_log_level(severity)

    message = format_error_log(error, context, include_trace)

    if include_trace and log_level >= logging.ERROR:
        logger.log(log_level, message, exc_info=True)
    else:
        logger.log(log_level, message)


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
    def __init__(self, message: str = "Rate limit exceeded", **kwargs):
        super().__init__(message, ErrorType.RATELIMIT, ErrorSeverity.MEDIUM, **kwargs)


class SeedTimeoutError(SeedAgentError):
    """超时错误（避免与内置 TimeoutError 冲突）"""
    def __init__(self, message: str = "Operation timed out", **kwargs):
        super().__init__(message, ErrorType.TIMEOUT, ErrorSeverity.MEDIUM, **kwargs)


class SeedConnectionError(SeedAgentError):
    """连接错误（避免与内置 ConnectionError 冲突）"""
    def __init__(self, message: str = "Connection failed", **kwargs):
        super().__init__(message, ErrorType.CONNECTION, ErrorSeverity.MEDIUM, **kwargs)


class ConfigurationError(SeedAgentError):
    """配置错误"""
    def __init__(self, message: str = "Configuration error", **kwargs):
        super().__init__(message, ErrorType.CONFIG, ErrorSeverity.HIGH, **kwargs)


# 向后兼容别名（deprecated，将在未来版本移除）
TimeoutError = SeedTimeoutError
ConnectionError = SeedConnectionError

__all__ = [
    "ErrorType",
    "ErrorSeverity",
    "classify_error",
    "get_log_level",
    "format_error_log",
    "log_error",
    "SeedAgentError",
    "RateLimitError",
    "SeedTimeoutError",
    "SeedConnectionError",
    "ConfigurationError",
    # 向后兼容
    "TimeoutError",
    "ConnectionError",
]