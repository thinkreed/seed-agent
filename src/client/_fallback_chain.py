"""
跨 Provider 降级链模块

提供:
- FallbackChain: Provider 故障转移链

借鉴 CodeBrain 架构设计的优雅降级机制。
"""

import asyncio
import logging

from openai import AsyncOpenAI

logger = logging.getLogger("seed_agent")


class FallbackChain:
    """跨 Provider 降级链：primary 失败时自动切换到 fallback

    借鉴 CodeBrain 架构设计的优雅降级机制。

    并发安全：使用 asyncio.Lock 保护状态变更

    Attributes:
        _providers: Provider 优先级列表 [primary, fallback1, fallback2, ...]
        _clients: Provider 到 AsyncOpenAI 实例的映射
        _active_provider: 当前活跃的 provider（缓存）
        _status: 当前状态 (healthy, degraded, unavailable)
        _lock: asyncio.Lock 用于并发安全
    """

    def __init__(self, providers: list[str], clients: dict[str, AsyncOpenAI]):
        self._providers = providers  # 优先级列表：[primary, fallback1, fallback2, ...]
        self._clients = clients
        self._active_provider: str | None = None  # 当前活跃的 provider
        self._status: str = "healthy"  # healthy, degraded, unavailable
        self._lock = asyncio.Lock()  # 并发安全保护

    async def get_active_client(self) -> tuple[str, AsyncOpenAI]:
        """获取当前活跃的 provider 和 client（异步版本，线程安全）

        优化：使用缓存避免每次遍历

        Returns:
            (provider_name, AsyncOpenAI) 元组

        Raises:
            ValueError: 无可用 provider
        """
        async with self._lock:
            # 快速路径：已缓存活跃 provider
            if self._active_provider and self._active_provider in self._clients:
                return self._active_provider, self._clients[self._active_provider]

            # 遍历 providers 找到第一个可用的（跳过不在 clients 中的）
            for provider in self._providers:
                if provider in self._clients:
                    self._active_provider = provider
                    return provider, self._clients[provider]

            raise ValueError("No available provider")

    async def mark_degraded(self, failed_provider: str):
        """标记 provider 失败，切换到下一个（异步版本，线程安全）

        Args:
            failed_provider: 失败的 provider 名称
        """
        async with self._lock:
            logger.warning(f"Provider {failed_provider} failed, attempting fallback")

            # 清理缓存：确保不会返回已失效的 provider
            if self._active_provider == failed_provider:
                self._active_provider = None

            # 找到下一个可用 provider
            failed_idx = (
                self._providers.index(failed_provider)
                if failed_provider in self._providers
                else -1
            )
            for i, provider in enumerate(self._providers):
                if i > failed_idx and provider in self._clients:
                    self._active_provider = provider
                    self._status = "degraded"
                    logger.info(f"Switched to fallback provider: {provider}")
                    return

            # 无可用 fallback
            self._active_provider = None
            self._status = "unavailable"
            remaining_providers = len(self._providers)
            # 移除失败的 provider 防止 get_active_client 重新选中
            if failed_provider in self._providers:
                self._providers.remove(failed_provider)
            logger.error(
                f"All providers failed: failed_provider={failed_provider}, "
                f"remaining={remaining_providers - 1}, provider_chain={self._providers}"
            )

    async def mark_healthy(self, provider: str):
        """标记 provider 健康（异步版本，线程安全）

        Args:
            provider: 恢复健康的 provider 名称
        """
        async with self._lock:
            self._active_provider = provider
            self._status = "healthy"

    @property
    def status(self) -> str:
        """获取当前状态

        Returns:
            状态字符串 (healthy, degraded, unavailable)
        """
        return self._status
