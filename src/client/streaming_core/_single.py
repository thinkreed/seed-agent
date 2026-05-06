"""单次流式调用（含 thinking 支持）"""

import asyncio
import logging
from collections.abc import AsyncGenerator

from src.client.streaming_core._thinking import _parse_embedded_thinking

logger = logging.getLogger("seed_agent")


async def stream_chat_completion_single(
    client,
    model_config,
    messages: list[dict],
    **kwargs,
) -> AsyncGenerator[dict, None]:
    """单 provider 流式调用（含 thinking 支持）

    Args:
        client: AsyncOpenAI 实例
        model_config: 模型配置
        messages: 消息列表
        **kwargs: 其他参数

    Yields:
        流式数据块，包含以下类型：
        - {"type": "thinking", "content": "..."} - 思考过程片段
        - {"type": "content", "content": "..."} - 正式回复片段
        - 原始 OpenAI 格式 chunk（保持向后兼容）
    """
    # 清理空 tools 数组（部分 API 不允许空数组）
    tools = kwargs.get("tools")
    if not tools:
        kwargs.pop("tools", None)

    response = await client.chat.completions.create(
        model=model_config.id,
        messages=messages,  # type: ignore[arg-type]
        stream=True,
        max_tokens=model_config.maxTokens,
        **kwargs,
    )

    # 兼容不同 SDK 版本：AsyncStream vs 协程包装
    if hasattr(response, "__aiter__"):
        stream = response
    elif asyncio.iscoroutine(response):
        stream = await response
    else:
        # 非流式响应，直接 yield 并返回
        try:
            yield response.model_dump()
        except Exception as e:
            logger.debug(f"Failed to serialize response: {type(e).__name__}")
            yield {"error": str(response)}
        return

    async for chunk in stream:
        try:
            chunk_dict = chunk.model_dump()
            if chunk_dict.get("choices"):
                choices = chunk_dict["choices"]
                delta = choices[0].get("delta", {})

                # 识别 thinking/reasoning_content 字段
                thinking_content = _extract_thinking_from_delta(delta)

                # 先 yield thinking chunk
                if thinking_content:
                    yield {"type": "thinking", "content": thinking_content}

                # 处理 content（可能含嵌入标签）
                content = _extract_content_from_delta(delta)
                if content:
                    parsed_thinking, parsed_content = _parse_embedded_thinking(content)
                    if parsed_thinking:
                        yield {"type": "thinking", "content": parsed_thinking}
                    if parsed_content:
                        yield {"type": "content", "content": parsed_content}

                # 同时 yield 原始 chunk（向后兼容）
                yield chunk_dict
        except Exception as e:
            logger.debug(f"Failed to serialize stream chunk: {type(e).__name__}")
            continue


def _extract_thinking_from_delta(delta) -> str | None:
    """从 delta 中提取 thinking 内容"""
    if hasattr(delta, "thinking") and delta.thinking:
        return delta.thinking
    if hasattr(delta, "reasoning_content") and delta.reasoning_content:
        return delta.reasoning_content
    if isinstance(delta, dict):
        return delta.get("thinking") or delta.get("reasoning_content")
    return None


def _extract_content_from_delta(delta) -> str:
    """从 delta 中提取 content 内容"""
    if isinstance(delta, dict):
        return delta.get("content", "")
    return getattr(delta, "content", "")