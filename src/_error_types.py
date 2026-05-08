"""
错误类型定义和分类逻辑

提供:
1. 错误类型枚举 (ErrorType)
2. 错误严重程度枚举 (ErrorSeverity)
3. 错误分类规则和函数

使用方式:
    from src._error_types import ErrorType, ErrorSeverity, classify_error
"""

from enum import Enum


class ErrorType(Enum):
    """错误类型枚举"""

    RATELIMIT = "ratelimit"  # API 限流
    TIMEOUT = "timeout"  # 超时
    CONNECTION = "connection"  # 网络/连接错误
    CONTEXT_OVERFLOW = "context"  # 上下文窗口溢出
    PERMISSION = "permission"  # 权限错误
    NOT_FOUND = "not_found"  # 资源不存在
    VALIDATION = "validation"  # 数据验证错误
    CONFIG = "config"  # 配置错误
    API_ERROR = "api_error"  # 其他 API 错误
    INTERNAL = "internal"  # 内部错误


class ErrorSeverity(Enum):
    """错误严重程度"""

    LOW = "low"  # 可忽略/自动恢复
    MEDIUM = "medium"  # 需要关注/可能影响功能
    HIGH = "high"  # 严重/需要立即处理
    CRITICAL = "critical"  # 致命/系统不可用


# 错误类型识别规则（按优先级排序）
_ERROR_TYPE_RULES: list[tuple[ErrorType, list[str], ErrorSeverity]] = [
    # 高优先级错误
    (
        ErrorType.RATELIMIT,
        ["rate limit", "429", "too many requests"],
        ErrorSeverity.MEDIUM,
    ),
    (
        ErrorType.TIMEOUT,
        ["timeout", "timed out", "deadline exceeded"],
        ErrorSeverity.MEDIUM,
    ),
    (
        ErrorType.CONNECTION,
        ["connection", "connect", "network", "socket", "dns", "refused"],
        ErrorSeverity.MEDIUM,
    ),
    (
        ErrorType.PERMISSION,
        ["permission", "access denied", "unauthorized", "forbidden", "403"],
        ErrorSeverity.HIGH,
    ),
    (
        ErrorType.NOT_FOUND,
        ["not found", "404", "does not exist", "no such"],
        ErrorSeverity.LOW,
    ),
    # 中优先级错误
    (
        ErrorType.CONTEXT_OVERFLOW,
        ["context", "overflow", "too long", "maximum context", "token limit"],
        ErrorSeverity.HIGH,
    ),
    (
        ErrorType.VALIDATION,
        ["validation", "invalid", "malformed", "parse error", "json"],
        ErrorSeverity.MEDIUM,
    ),
    (
        ErrorType.CONFIG,
        ["config", "configuration", "missing key", "invalid value"],
        ErrorSeverity.HIGH,
    ),
    # 低优先级（兜底）
    (
        ErrorType.API_ERROR,
        ["api", "server", "500", "502", "503", "internal"],
        ErrorSeverity.MEDIUM,
    ),
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
    for err_type, _, severity in _ERROR_TYPE_RULES:
        if err_type.value in error_class:
            return err_type, severity

    # 检查错误消息关键词
    for err_type, keywords, severity in _ERROR_TYPE_RULES:
        if any(kw in error_str for kw in keywords):
            return err_type, severity

    # 默认：内部错误
    return ErrorType.INTERNAL, ErrorSeverity.MEDIUM


__all__ = [
    "ErrorSeverity",
    "ErrorType",
    "classify_error",
]