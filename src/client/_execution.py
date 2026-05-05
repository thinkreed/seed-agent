"""
执行层模块

提供:
- chat_completion_single: 单 Provider 调用
- try_provider_with_retry: 尝试单个 provider 调用（带重试）
- try_fallback_providers: 尝试所有 fallback providers
- chat_completion_with_fallback_internal: 带降级的非流式聊天补全
- get_fallback_model_id: 获取 fallback provider 的等效模型
- iterate_fallback_models: 生成 fallback provider 和 model_id 列表
"""

import asyncio
import logging
import time

from openai import APIConnectionError, APIStatusError, RateLimitError

from src.client._fallback_chain import FallbackChain
from src.client._observability import (
    create_llm_span,
    handle_llm_error,
    record_success_metrics,
)
from src.client._retry import get_retry_wait_time, should_continue_retry
from src.client._utils import _calc_duration_ms
from src.observability import add_fallback_event

logger = logging.getLogger("seed_agent")


async def chat_completion_single(
    client,
    model_config,
    messages: list[dict],
    **kwargs,
) -> dict:
    """单 provider 调用

    Args:
        client: AsyncOpenAI 实例
        model_config: 模型配置
        messages: 消息列表
        **kwargs: 其他参数

    Returns:
        响应字典
    """
    # 清理空 tools 数组（部分 API 不允许空数组）
    tools = kwargs.get("tools")
    if not tools:
        kwargs.pop("tools", None)

    response = await client.chat.completions.create(
        model=model_config.id,
        messages=messages,  # type: ignore[arg-type]
        max_tokens=model_config.maxTokens,
        **kwargs,
    )
    return response.model_dump()


def get_fallback_model_id(
    original_model_id: str,
    fallback_provider: str,
    config_models: dict,
) -> str | None:
    """获取 fallback provider 的等效模型

    Args:
        original_model_id: 原始模型 ID
        fallback_provider: Fallback provider 名称
        config_models: 配置模型字典

    Returns:
        Fallback 模型 ID 或 None
    """
    _, model_name = original_model_id.split("/", 1)

    # 尝试在 fallback provider 找同名模型
    if fallback_provider in config_models:
        for model in config_models[fallback_provider].models:
            if model.id == model_name:
                return f"{fallback_provider}/{model_name}"

    # 返回 fallback provider 的第一个模型
    if fallback_provider in config_models:
        first_model = config_models[fallback_provider].models[0]
        return f"{fallback_provider}/{first_model.id}"

    return None


def iterate_fallback_models(
    model_id: str,
    exclude_provider: str,
    fallback_chain: FallbackChain | None,
    clients: dict,
    config_models: dict,
) -> list[tuple[str, str]]:
    """生成 fallback provider 和 model_id 列表

    Args:
        model_id: 原始模型 ID
        exclude_provider: 排除的 provider
        fallback_chain: 降级链
        clients: 客户端字典
        config_models: 配置模型字典

    Returns:
        (fallback_provider, fallback_model_id) 元组列表
    """
    fallbacks: list[tuple[str, str]] = []
    if not fallback_chain:
        return fallbacks

    for fallback_provider in fallback_chain._providers:
        if fallback_provider == exclude_provider:
            continue
        if fallback_provider not in clients:
            continue

        fallback_model_id = get_fallback_model_id(
            model_id, fallback_provider, config_models
        )
        if fallback_model_id:
            fallbacks.append((fallback_provider, fallback_model_id))

    return fallbacks


async def try_provider_with_retry(
    model_id: str,
    messages: list[dict],
    provider_id: str,
    get_client_func,
    get_model_config_func,
    **kwargs,
) -> tuple[bool, dict | None]:
    """尝试单个 provider 调用（带重试）

    Args:
        model_id: 模型 ID
        messages: 消息列表
        provider_id: Provider ID
        get_client_func: 获取客户端的函数
        get_model_config_func: 获取模型配置的函数
        **kwargs: 其他参数

    Returns:
        (success, result) - success 为 True 表示成功
    """
    for attempt in range(3):
        try:
            client = await get_client_func(model_id)
            model_config = get_model_config_func(model_id)
            result = await chat_completion_single(client, model_config, messages, **kwargs)
            return True, result
        except (APIConnectionError, RateLimitError, APIStatusError) as e:
            if should_continue_retry(attempt):
                wait_time = get_retry_wait_time(attempt, e)
                logger.warning(f"Retry {attempt + 1}/3 after {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
            else:
                logger.warning(f"Provider {provider_id} exhausted retries")
                break
    return False, None


async def try_fallback_providers(
    span,
    model_id: str,
    messages: list[dict],
    start_time: float,
    fallback_chain: FallbackChain,
    clients: dict,
    config_models: dict,
    get_client_func,
    get_model_config_func,
    **kwargs,
) -> tuple[bool, dict | None]:
    """尝试所有 fallback providers

    Args:
        span: OpenTelemetry span
        model_id: 模型 ID
        messages: 消息列表
        start_time: 开始时间
        fallback_chain: 降级链
        clients: 客户端字典
        config_models: 配置模型字典
        get_client_func: 获取客户端的函数
        get_model_config_func: 获取模型配置的函数
        **kwargs: 其他参数

    Returns:
        (success, result) - success 为 True 表示成功
    """
    if not fallback_chain:
        return False, None

    exclude_provider = model_id.split("/", maxsplit=1)[0]

    for fallback_provider, fallback_model_id in iterate_fallback_models(
        model_id, exclude_provider, fallback_chain, clients, config_models
    ):
        if span:
            add_fallback_event(
                span,
                from_provider=exclude_provider,
                to_provider=fallback_provider,
                reason="provider_degraded",
                attempt=fallback_chain._providers.index(fallback_provider),
            )

        try:
            logger.info(f"Trying fallback: {fallback_model_id}")
            client = await get_client_func(fallback_model_id)
            model_config = get_model_config_func(fallback_model_id)
            result = await chat_completion_single(client, model_config, messages, **kwargs)
            await fallback_chain.mark_healthy(fallback_provider)

            duration_ms = _calc_duration_ms(start_time)
            usage = result.get("usage")
            record_success_metrics(span, fallback_provider, fallback_model_id, usage, duration_ms)

            return True, result
        except Exception as fallback_e:
            logger.warning(f"Fallback {fallback_provider} failed: {fallback_e}")
            await fallback_chain.mark_degraded(fallback_provider)

    return False, None


async def chat_completion_with_fallback_internal(
    model_id: str,
    messages: list[dict],
    fallback_chain: FallbackChain | None,
    clients: dict,
    config_models: dict,
    get_client_func,
    get_model_config_func,
    get_active_provider_func,
    **kwargs,
) -> dict:
    """内部方法：带跨 Provider 降级的非流式聊天补全

    Args:
        model_id: 模型 ID
        messages: 消息列表
        fallback_chain: 降级链
        clients: 客户端字典
        config_models: 配置模型字典
        get_client_func: 获取客户端的函数
        get_model_config_func: 获取模型配置的函数
        get_active_provider_func: 获取活跃 provider 的函数
        **kwargs: 其他参数

    Returns:
        响应字典

    Raises:
        RuntimeError: 所有 providers 都失败
    """
    provider_id = model_id.split("/", maxsplit=1)[0]
    active_provider = await get_active_provider_func()
    start_time = time.time()

    span = create_llm_span(model_id, active_provider, streaming=False)

    try:
        success, result = await try_provider_with_retry(
            model_id, messages, provider_id,
            get_client_func, get_model_config_func,
            **kwargs
        )

        if success:
            if fallback_chain:
                await fallback_chain.mark_healthy(provider_id)

            duration_ms = _calc_duration_ms(start_time)
            usage = result.get("usage") if result else None
            record_success_metrics(span, active_provider, model_id, usage, duration_ms)
            return result  # type: ignore[return-value]

        if fallback_chain:
            await fallback_chain.mark_degraded(provider_id)
            fallback_success, fallback_result = await try_fallback_providers(
                span, model_id, messages, start_time,
                fallback_chain, clients, config_models,
                get_client_func, get_model_config_func,
                **kwargs
            )
            if fallback_success and fallback_result:
                return fallback_result

        raise RuntimeError(f"All providers failed: model={model_id}")

    except Exception as e:
        handle_llm_error(span, active_provider, model_id, start_time, e)
        raise
    finally:
        if span:
            span.end()
