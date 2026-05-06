"""重试调用模块

提供 try_provider_with_retry 函数，执行带重试的 Provider 调用。
"""

import asyncio
import logging

from openai import APIConnectionError, APIStatusError, RateLimitError

from src.client._retry import get_retry_wait_time, should_continue_retry
from src.client.execution_core._single import chat_completion_single

logger = logging.getLogger("seed_agent")


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
            result = await chat_completion_single(
                client, model_config, messages, **kwargs
            )
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