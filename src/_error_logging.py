"""
错误日志格式化

提供:
1. 日志级别映射
2. 标准化日志格式
3. 统一错误日志记录

使用方式:
    from src._error_logging import log_error, format_error_log
"""

import logging

from ._error_types import ErrorSeverity, ErrorType, classify_error


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
    _error_type, severity = classify_error(error)
    log_level = get_log_level(severity)

    message = format_error_log(error, context, include_trace)

    if include_trace and log_level >= logging.ERROR:
        logger.log(log_level, message, exc_info=True)
    else:
        logger.log(log_level, message)


__all__ = [
    "format_error_log",
    "get_log_level",
    "log_error",
]