"""
通用工具函数

提供类型安全转换等辅助功能。
"""

from typing import Any


def safe_int_convert(value: Any, default: int = 0, min_val: int | None = None) -> int:
    """安全转换整数

    Args:
        value: 输入值（可能是字符串、整数等）
        default: 默认值（转换失败时使用）
        min_val: 最小值限制（可选）

    Returns:
        转换后的整数
    """
    try:
        if isinstance(value, int):
            result = value
        elif isinstance(value, str):
            result = int(value.strip())
        elif isinstance(value, float):
            result = int(value)
        else:
            result = default

        if min_val is not None and result < min_val:
            result = min_val

        return result
    except (ValueError, TypeError):
        return default


def truncate_text(text: str, max_length: int = 500) -> str:
    """截断文本

    Args:
        text: 输入文本
        max_length: 最大长度

    Returns:
        截断后的文本
    """
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def format_duration_ms(duration_ms: float) -> str:
    """格式化持续时间

    Args:
        duration_ms: 毫秒数

    Returns:
        格式化字符串
    """
    if duration_ms < 1000:
        return f"{duration_ms:.2f}ms"
    elif duration_ms < 60000:
        return f"{duration_ms / 1000:.2f}s"
    else:
        return f"{duration_ms / 60000:.2f}m"