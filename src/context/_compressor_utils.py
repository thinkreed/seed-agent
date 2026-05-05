"""
上下文压缩工具函数

包含消息处理、Token估算、简化等辅助函数

重构说明:
- 原实现已拆分为独立模块以提高可维护性
- 此文件保持向后兼容，从新模块导入所有内容
"""

from src.context._compressor_token import (
    build_history_from_session,
    estimate_tokens,
    event_to_message,
)
from src.context._compressor_format import (
    extract_key_info,
    format_abstract,
    format_messages_for_summary,
    format_simplified,
    simplify_messages,
)

__all__ = [
    "estimate_tokens",
    "event_to_message",
    "build_history_from_session",
    "simplify_messages",
    "extract_key_info",
    "format_simplified",
    "format_abstract",
    "format_messages_for_summary",
]