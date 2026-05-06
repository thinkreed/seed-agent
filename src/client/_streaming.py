"""
流式响应处理模块

提供:
- stream_chat_completion_single: 单 Provider 流式调用（含 thinking 支持）
- stream_with_retry: 流式响应重试逻辑
- stream_fallback_providers: 流式 fallback providers 尝试
- stream_chat_completion_with_fallback_internal: 带降级的流式聊天补全

Thinking 支持：
- Claude: delta.thinking 字段
- OpenAI o-series: delta.reasoning_content 字段
- Qwen: 可能在 content 中嵌入 <thinking> 标签
"""

import asyncio
import logging
import re
from collections.abc import AsyncGenerator

from openai import APIConnectionError, APIStatusError, RateLimitError

from src.client._fallback_chain import FallbackChain
from src.client._retry import get_retry_wait_time, should_continue_retry
from src.client._utils import _calc_duration_ms, _estimate_stream_tokens
from src.observability import StatusCode, add_fallback_event, record_llm_success
from src.rate_limiter import RateLimiter

logger = logging.getLogger("seed_agent")

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
        remaining = content[:match.start()] + content[match.end():]
        return thinking, remaining.strip()
    return None, content


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
                thinking_content = None
                if hasattr(delta, "thinking") and delta.thinking:
                    thinking_content = delta.thinking
                elif hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    thinking_content = delta.reasoning_content
                elif isinstance(delta, dict):
                    thinking_content = delta.get("thinking") or delta.get("reasoning_content")

                # 先 yield thinking chunk
                if thinking_content:
                    yield {"type": "thinking", "content": thinking_content}

                # 处理 content（可能含嵌入标签）
                content = delta.get("content", "") if isinstance(delta, dict) else getattr(delta, "content", "")
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


async def stream_with_retry(
    model_id: str,
    messages: list[dict],
    fallback_chain: FallbackChain | None,
    rate_limiter: RateLimiter | None,
    span,
    active_provider: str,
    start_time: float,
    get_client_func,
    get_model_config_func,
    stream_chat_completion_single_func,
    **kwargs,
) -> AsyncGenerator[dict, None]:
    """流式响应重试逻辑

    Args:
        model_id: 模型 ID
        messages: 消息列表
        fallback_chain: 降级链
        rate_limiter: 限流器
        span: OpenTelemetry span
        active_provider: 活跃 provider
        start_time: 开始时间
        get_client_func: 获取客户端的函数
        get_model_config_func: 获取模型配置的函数
        stream_chat_completion_single_func: 流式单次调用函数
        **kwargs: 其他参数

    Yields:
        流式数据块
    """
    chunk_count = 0  # Initialize before retry loop to avoid UnboundLocalError
    for attempt in range(3):
        try:
            chunk_count = 0  # Reset for each attempt
            client = await get_client_func(model_id)
            model_config = get_model_config_func(model_id)
            async for chunk in stream_chat_completion_single_func(
                client, model_config, messages, **kwargs
            ):
                yield chunk
                chunk_count += 1

            if fallback_chain:
                await fallback_chain.mark_healthy(active_provider)

            # 流式 token 估算
            duration_ms = _calc_duration_ms(start_time)
            estimated_tokens = _estimate_stream_tokens(chunk_count)

            record_llm_success(
                provider=active_provider,
                model=model_id,
                input_tokens=0,
                output_tokens=estimated_tokens,
                duration_ms=duration_ms,
            )

            if span:
                span.set_attribute("gen_ai.usage.output_tokens", estimated_tokens)
                span.set_attribute("seed.streaming", True)
                span.set_status(StatusCode.OK)

            return

        except (APIConnectionError, RateLimitError, APIStatusError) as e:
            # Safety check: Do not retry if partial stream was already yielded
            # to avoid duplicate data in the consumer
            if chunk_count > 0:
                logger.warning(
                    f"Stream failed after {chunk_count} chunks, cannot safely retry"
                )
                raise

            if should_continue_retry(attempt):
                wait_time = get_retry_wait_time(attempt, e)
                logger.warning(f"Retry {attempt + 1}/3 after {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
            else:
                logger.warning(f"Provider {active_provider} exhausted retries")
                raise


async def stream_fallback_providers(
    model_id: str,
    messages: list[dict],
    fallback_chain: FallbackChain,
    clients: dict,
    config_models: dict,
    span,
    active_provider: str,
    start_time: float,
    exclude_provider: str,
    get_client_func,
    get_model_config_func,
    get_fallback_model_id_func,
    stream_chat_completion_single_func,
    **kwargs,
) -> AsyncGenerator[dict, None]:
    """流式 fallback providers 尝试

    Args:
        model_id: 模型 ID
        messages: 消息列表
        fallback_chain: 降级链
        clients: 客户端字典
        config_models: 配置模型字典
        span: OpenTelemetry span
        active_provider: 活跃 provider
        start_time: 开始时间
        exclude_provider: 排除的 provider
        get_client_func: 获取客户端的函数
        get_model_config_func: 获取模型配置的函数
        get_fallback_model_id_func: 获取 fallback 模型 ID 的函数
        stream_chat_completion_single_func: 流式单次调用函数
        **kwargs: 其他参数

    Yields:
        流式数据块

    Raises:
        RuntimeError: Fallback chain 未初始化
    """
    # 确保 fallback_chain 已初始化（显式检查避免优化模式问题）
    if fallback_chain is None:
        raise RuntimeError(
            "Fallback chain not initialized - "
            "check _init_fallback_chain() was called during construction"
        )

    for fallback_provider in fallback_chain._providers:
        if fallback_provider == exclude_provider:
            continue
        if fallback_provider not in clients:
            continue

        fallback_model_id = get_fallback_model_id_func(model_id, fallback_provider)
        if not fallback_model_id:
            continue

        if span:
            add_fallback_event(
                span,
                from_provider=active_provider,
                to_provider=fallback_provider,
                reason="stream_failure",
                attempt=fallback_chain._providers.index(fallback_provider),
            )

        try:
            logger.info(f"Trying fallback stream: {fallback_model_id}")
            client = await get_client_func(fallback_model_id)
            model_config = get_model_config_func(fallback_model_id)
            chunk_count = 0
            async for chunk in stream_chat_completion_single_func(
                client, model_config, messages, **kwargs
            ):
                yield chunk
                chunk_count += 1

            await fallback_chain.mark_healthy(fallback_provider)

            # 流式成功 Metrics
            duration_ms = _calc_duration_ms(start_time)
            estimated_tokens = _estimate_stream_tokens(chunk_count)

            record_llm_success(
                provider=fallback_provider,
                model=fallback_model_id,
                input_tokens=0,
                output_tokens=estimated_tokens,
                duration_ms=duration_ms,
            )

            if span:
                span.set_attribute("gen_ai.usage.output_tokens", estimated_tokens)
                span.set_attribute("seed.provider", fallback_provider)
                span.set_status(StatusCode.OK)

            return

        except Exception as fallback_e:
            logger.warning(f"Fallback {fallback_provider} failed: {fallback_e}")
            await fallback_chain.mark_degraded(fallback_provider)
