"""非流式执行模块

提供:
- chat_completion_single: 单 Provider 调用
- try_provider_with_retry: 尝试单个 provider 调用（带重试）
- try_fallback_providers: 尝试所有 fallback providers
- get_fallback_model_id: 获取 fallback provider 的等效模型
- iterate_fallback_models: 生成 fallback provider 和 model_id 列表
- chat_completion_with_fallback_internal: 带降级的非流式聊天补全
"""

import time

from src.client._fallback_chain import FallbackChain
from src.client._observability import (
    create_llm_span,
    handle_llm_error,
    record_success_metrics,
)
from src.client._utils import _calc_duration_ms
from src.client.execution_core._fallback import (
    get_fallback_model_id,
    iterate_fallback_models,
    try_fallback_providers,
)
from src.client.execution_core._retry import try_provider_with_retry
from src.client.execution_core._single import chat_completion_single

__all__ = [
    "chat_completion_single",
    "chat_completion_with_fallback_internal",
    "get_fallback_model_id",
    "iterate_fallback_models",
    "try_fallback_providers",
    "try_provider_with_retry",
]


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
            model_id,
            messages,
            provider_id,
            get_client_func,
            get_model_config_func,
            **kwargs,
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
                span,
                model_id,
                messages,
                start_time,
                fallback_chain,
                clients,
                config_models,
                get_client_func,
                get_model_config_func,
                **kwargs,
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