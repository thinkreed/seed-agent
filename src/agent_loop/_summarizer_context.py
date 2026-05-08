"""
Summarizer 上下文估算

提取 estimate_context_size 和 should_summarize 方法。
"""

import json
from typing import Any


def estimate_context_size(
    messages: list[dict[str, Any]],
    system_prompt: str | None = None,
    encoding: Any = None,
) -> int:
    """估算上下文 Token 数

    Args:
        messages: 消息列表
        system_prompt: 系统提示
        encoding: 编码器

    Returns:
        Token 数
    """
    total = 0

    if system_prompt:
        total += _encode_text(system_prompt, encoding)

    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += _encode_text(content, encoding)
        if msg.get("tool_calls"):
            total += _encode_text(json.dumps(msg["tool_calls"]), encoding)

    return total


def _encode_text(text: str, encoding: Any = None) -> int:
    """编码文本返回 token 数"""
    if encoding:
        return len(encoding.encode(text))
    return int(len(text) * 0.7)


def should_summarize(
    estimated_tokens: int,
    conversation_rounds: int,
    context_window: int,
    summary_interval: int,
    context_usage_threshold: float = 0.75,
) -> tuple[bool, bool]:
    """检查是否需要摘要

    Args:
        estimated_tokens: 估算的 Token 数
        conversation_rounds: 对话轮数
        context_window: 上下文窗口大小
        summary_interval: 摘要间隔
        context_usage_threshold: 上下文使用阈值

    Returns:
        (is_context_full, should_summarize)
    """
    token_threshold = context_window * context_usage_threshold
    is_context_full = estimated_tokens > token_threshold
    is_round_limit_reached = conversation_rounds >= summary_interval
    return is_context_full, (is_context_full or is_round_limit_reached)


__all__ = ["estimate_context_size", "should_summarize"]