"""Provider 配置和客户端工厂

负责创建和销毁临时客户端实例
"""

import logging
import time
from typing import Any

from src.security.proxy._temp_client import TemporaryClient

logger = logging.getLogger(__name__)

# Provider 配置
PROVIDER_CONFIGS: dict[str, dict[str, str | None]] = {
    "openai": {
        "base_url": None,
        "client_class": "AsyncOpenAI",
    },
    "anthropic": {
        "base_url": None,
        "client_class": "AsyncAnthropic",
    },
    "bailian": {
        "base_url": "https://coding.dashscope.aliyuncs.com/v1",
        "client_class": "AsyncOpenAI",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "client_class": "AsyncOpenAI",
    },
}


async def create_temp_client(
    provider: str,
    credential: str,
) -> TemporaryClient:
    """创建临时客户端

    重要: 客户端不存储在 Sandbox 中

    Args:
        provider: 提供商名称
        credential: 凭证值

    Returns:
        TemporaryClient 实例

    Raises:
        ValueError: Provider 不支持
    """
    config = PROVIDER_CONFIGS.get(provider)
    if not config:
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Supported providers: {list(PROVIDER_CONFIGS.keys())}"
        )

    client_class = config["client_class"]
    base_url = config.get("base_url")

    # 创建客户端实例
    if client_class == "AsyncOpenAI":
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=credential,
            base_url=base_url,
        )
    elif client_class == "AsyncAnthropic":
        try:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=credential)
        except ImportError as e:
            raise ValueError(
                "anthropic package not installed. "
                "Install with: pip install anthropic"
            ) from e
    else:
        raise ValueError(f"Unsupported client class: {client_class}")

    temp_client = TemporaryClient(
        provider=provider,
        client=client,
        credential=credential,
        created_at=time.time(),
    )

    logger.debug(
        f"Temporary client created: provider={provider}, "
        f"base_url={base_url or 'default'}"
    )

    return temp_client


def destroy_temp_client(temp_client: TemporaryClient) -> None:
    """销毁临时客户端

    凭证销毁: 客户端对象被丢弃，凭证不再可用
    """
    temp_client.destroy()

    logger.debug(
        f"Temporary client destroyed: provider={temp_client.provider}, "
        f"lifetime={temp_client.lifetime_ms:.2f}ms"
    )


def get_supported_providers() -> list[str]:
    """获取支持的 Provider 列表"""
    return list(PROVIDER_CONFIGS.keys())


def register_provider(
    provider: str,
    base_url: str | None,
    client_class: str = "AsyncOpenAI",
) -> None:
    """注册新的 Provider

    Args:
        provider: Provider 名称
        base_url: API 基础 URL
        client_class: 客户端类名
    """
    PROVIDER_CONFIGS[provider] = {
        "base_url": base_url,
        "client_class": client_class,
    }

    logger.info(f"Provider registered: {provider}, base_url={base_url}")