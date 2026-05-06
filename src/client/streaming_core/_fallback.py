"""流式 fallback providers 尝试"""

import logging
from collections.abc import AsyncGenerator

from src.client._fallback_chain import FallbackChain
from src.client._utils import _calc_duration_ms, _estimate_stream_tokens
from src.observability import StatusCode, add_fallback_event, record_llm_success

logger = logging.getLogger("seed_agent")


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
            async for chunk in _try_fallback_stream(
                fallback_model_id=fallback_model_id,
                fallback_provider=fallback_provider,
                messages=messages,
                fallback_chain=fallback_chain,
                start_time=start_time,
                span=span,
                get_client_func=get_client_func,
                get_model_config_func=get_model_config_func,
                stream_chat_completion_single_func=stream_chat_completion_single_func,
                **kwargs,
            ):
                yield chunk
            return  # 成功，退出
        except Exception as fallback_e:
            logger.warning(f"Fallback {fallback_provider} failed: {fallback_e}")
            await fallback_chain.mark_degraded(fallback_provider)


async def _try_fallback_stream(
    fallback_model_id: str,
    fallback_provider: str,
    messages: list[dict],
    fallback_chain: FallbackChain,
    start_time: float,
    span,
    get_client_func,
    get_model_config_func,
    stream_chat_completion_single_func,
    **kwargs,
) -> AsyncGenerator[dict, None]:
    """尝试单个 fallback provider 的流式调用"""
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

    # 记录成功 metrics
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