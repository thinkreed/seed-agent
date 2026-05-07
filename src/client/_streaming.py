"""流式响应处理模块（聚合层）

重新导出 streaming_core 子模块的公共 API，保持向后兼容。

提供:
- stream_chat_completion_single: 单 Provider 流式调用（含 thinking 支持）
- stream_with_retry: 流式响应重试逻辑
- stream_fallback_providers: 流式 fallback providers 尝试
"""

# 从子模块重新导出，保持向后兼容
from src.client.streaming_core import (
    _parse_embedded_thinking,
    stream_chat_completion_single,
    stream_fallback_providers,
    stream_with_retry,
)

__all__ = [
    "_parse_embedded_thinking",
    "stream_chat_completion_single",
    "stream_fallback_providers",
    "stream_with_retry",
]