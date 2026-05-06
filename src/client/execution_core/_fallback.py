"""Fallback Provider 调用模块

提供 fallback 相关函数：
- get_fallback_model_id: 获取 fallback provider 的等效模型
- iterate_fallback_models: 生成 fallback provider 和 model_id 列表
- try_fallback_providers: 尝试所有 fallback providers
"""

import logging

from src.client._fallback_chain import FallbackChain
from src.client._observability import record_success_metrics
from src.client._utils import _calc_duration_ms
from src.client.execution_core._single import chat_completion_single
from src.observability import add_fallback_event

logger = logging.getLogger("seed_agent")


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
            result = await chat_completion_single(
                client, model_config, messages, **kwargs
            )
            await fallback_chain.mark_healthy(fallback_provider)

            duration_ms = _calc_duration_ms(start_time)
            usage = result.get("usage")
            record_success_metrics(
                span, fallback_provider, fallback_model_id, usage, duration_ms
            )

            return True, result
        except Exception as fallback_e:
            logger.warning(f"Fallback {fallback_provider} failed: {fallback_e}")
            await fallback_chain.mark_degraded(fallback_provider)

    return False, None