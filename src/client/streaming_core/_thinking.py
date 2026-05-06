"""Thinking 标签解析逻辑

支持：
- Claude: delta.thinking 字段
- OpenAI o-series: delta.reasoning_content 字段
- Qwen: 可能在 content 中嵌入 <thinking> 标签
"""

import re

# Thinking 标签解析正则（用于 Qwen 等模型）
_THINKING_TAG_PATTERN = re.compile(r"<thinking>(.*?)</thinking>", re.DOTALL)


def _parse_embedded_thinking(content: str) -> tuple[str | None, str]:
    """解析嵌入在 content 中的 thinking 标签

    Args:
        content: 可能包含 <thinking> 标签的文本

    Returns:
        (thinking_content, remaining_content) 元组
    """
    match = _THINKING_TAG_PATTERN.search(content)
    if match:
        thinking = match.group(1).strip()
        remaining = content[: match.start()] + content[match.end() :]
        return thinking, remaining.strip()
    return None, content