"""
凭证隔离沙盒 - 输出清洗模块

负责:
- 过滤输出中的凭证
- API Key 模式替换
- 安全日志输出
"""

from src.security.credential_isolated._types import (
    _RE_API_KEY_GENERIC,
    _RE_AWS_KEY,
    _RE_BEARER,
    _RE_SK_KEY,
)


def sanitize_output(output: str) -> str:
    """过滤输出中的凭证

    移除或替换输出中可能包含的凭证值。

    Args:
        output: 原始输出

    Returns:
        过滤后的输出
    """
    # 过滤 API Key 模式 - 使用预编译正则
    # sk-* 模式 (OpenAI)
    output = _RE_SK_KEY.sub("[REDACTED_API_KEY]", output)

    # Bearer * 模式
    output = _RE_BEARER.sub("Bearer [REDACTED]", output)

    # AWS Access Key 模式
    output = _RE_AWS_KEY.sub("[REDACTED_AWS_KEY]", output)

    # 通用 API Key 模式
    return _RE_API_KEY_GENERIC.sub("api_key=[REDACTED]", output)


def sanitize_error_message(error_msg: str, max_length: int = 200) -> str:
    """清洗并截断错误消息

    Args:
        error_msg: 错误消息
        max_length: 最大长度

    Returns:
        安全的错误消息
    """
    sanitized = sanitize_output(error_msg)
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "...[truncated]"
    return sanitized