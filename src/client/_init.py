"""
初始化模块

提供:
- init_clients: 初始化各 provider 的 AsyncOpenAI 客户端
- build_model_config_cache: 构建模型配置缓存
- init_fallback_chain: 初始化降级链
- init_rate_limiting: 初始化限流组件
- init_state_persistence: 初始化状态持久化
"""

import asyncio
import logging

from src.client._fallback_chain import FallbackChain
from src.client._rate_limit_integration import load_queue_config
from src.client._timeout import TimeoutConfig
from src.client._utils import _resolve_api_key
from src.models import RateLimitConfig
from src.rate_limit_db import RateLimitSQLite

logger = logging.getLogger("seed_agent")


def init_clients(config, vault=None, async_openai_class=None) -> dict:
    """为每个 provider 初始化客户端

    Args:
        config: FullConfig 实例
        vault: CredentialVault 实例（可选）
        async_openai_class: AsyncOpenAI 类（可选，用于测试 mock）

    Returns:
        Provider 到 AsyncOpenAI 实例的映射
    """
    # 默认使用 openai.AsyncOpenAI，支持测试 mock
    if async_openai_class is None:
        from openai import AsyncOpenAI
        async_openai_class = AsyncOpenAI

    clients = {}
    for provider_id, provider_cfg in config.models.items():
        if provider_cfg.api == "openai-completions":
            api_key = _resolve_api_key(
                provider_cfg.apiKey, vault=vault, provider=provider_id
            )
            clients[provider_id] = async_openai_class(
                base_url=provider_cfg.baseUrl, api_key=api_key
            )
    return clients


def build_model_config_cache(config) -> dict:
    """构建模型配置缓存

    Args:
        config: FullConfig 实例

    Returns:
        模型 ID 到 ModelConfig 的映射
    """
    cache = {}
    for provider_id, provider_cfg in config.models.items():
        for model in provider_cfg.models:
            cache[f"{provider_id}/{model.id}"] = model
    return cache


def init_fallback_chain(clients: dict) -> FallbackChain | None:
    """初始化降级链

    Args:
        clients: Provider 到 AsyncOpenAI 实例的映射

    Returns:
        FallbackChain 实例或 None
    """
    providers = list(clients.keys())
    if providers:
        return FallbackChain(providers, clients)
    return None


def init_rate_limiting(config, rate_limiter_class=None, request_queue_class=None) -> tuple:
    """从配置初始化限流组件

    Args:
        config: FullConfig 实例
        rate_limiter_class: RateLimiter 类（可选，用于测试 mock）
        request_queue_class: RequestQueue 类（可选，用于测试 mock）

    Returns:
        (rate_config, semaphore, rate_limiter, request_queue, timeout_config) 元组
    """
    # 默认使用实际类，支持测试 mock
    if rate_limiter_class is None:
        from src.rate_limiter import RateLimiter
        rate_limiter_class = RateLimiter
    if request_queue_class is None:
        from src.request_queue import RequestQueue
        request_queue_class = RequestQueue

    # 获取第一个有 rateLimit 配置的 provider
    rate_config = None
    for provider_cfg in config.models.values():
        if provider_cfg.rateLimit:
            rate_config = provider_cfg.rateLimit
            break

    if rate_config is None:
        rate_config = RateLimitConfig()
        logger.info("Using default rate limit config")

    semaphore = asyncio.Semaphore(rate_config.maxConcurrent)
    rate_limiter = rate_limiter_class(
        rate=rate_config.get_effective_rate(),
        capacity=rate_config.burstCapacity,
        window_limit=rate_config.get_window_limit(),
        window_duration=rate_config.get_window_duration(),
    )
    request_queue = request_queue_class(config=load_queue_config(config))

    return rate_config, semaphore, rate_limiter, request_queue, TimeoutConfig()


def init_state_persistence() -> RateLimitSQLite:
    """初始化状态持久化

    Returns:
        RateLimitSQLite 实例
    """
    return RateLimitSQLite()
