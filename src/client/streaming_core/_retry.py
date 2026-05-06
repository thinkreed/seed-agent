"""流式响应重试逻辑"""

import asyncio
import logging
from collections.abc import AsyncGenerator

from openai import APIConnectionError, APIStatusError, RateLimitError

from src.client._fallback_chain import FallbackChain
from src.client._retry import get_retry_wait_time, should_continue_retry
from src.client._utils import _calc_duration_ms, _estimate_stream_tokens
from src.observability import StatusCode, record_llm_success
from src.rate_limiter import RateLimiter

logger = logging.getLogger("seed_agent")


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
    chunk_count = 0
    for attempt in range(3):
        try:
            chunk_count = 0
            client = await get_client_func(model_id)
            model_config = get_model_config_func(model_id)
            async for chunk in stream_chat_completion_single_func(
                client, model_config, messages, **kwargs
            ):
                yield chunk
                chunk_count += 1

            await _handle_stream_success(
                fallback_chain, active_provider, start_time, chunk_count, model_id, span
            )
            return

        except (APIConnectionError, RateLimitError, APIStatusError) as e:
            # 已有部分数据时不重试，避免重复
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


async def _handle_stream_success(
    fallback_chain: FallbackChain | None,
    active_provider: str,
    start_time: float,
    chunk_count: int,
    model_id: str,
    span,
) -> None:
    """处理流式成功"""
    if fallback_chain:
        await fallback_chain.mark_healthy(active_provider)

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