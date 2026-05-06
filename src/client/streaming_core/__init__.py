"""流式响应处理模块

提供:
- stream_chat_completion_single: 单 Provider 流式调用（含 thinking 支持）
- stream_with_retry: 流式响应重试逻辑
- stream_fallback_providers: 流式 fallback providers 尝试

Thinking 支持：
- Claude: delta.thinking 字段
- OpenAI o-series: delta.reasoning_content 字段
- Qwen: 可能在 content 中嵌入 <thinking> 标签
"""

from src.client.streaming_core._fallback import stream_fallback_providers
from src.client.streaming_core._retry import stream_with_retry
from src.client.streaming_core._single import stream_chat_completion_single
from src.client.streaming_core._thinking import _parse_embedded_thinking

__all__ = [
    "stream_chat_completion_single",
    "stream_with_retry",
    "stream_fallback_providers",
    "_parse_embedded_thinking",
]