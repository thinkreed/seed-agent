"""
Circuit Breaker Registry 模块

管理多个 Provider 的独立熔断器配置。
借鉴 worldmonitor 的"每个数据域独立熔断配置"设计。
"""

import asyncio
import logging
from typing import Any

from ._circuit_breaker import CircuitBreaker
from ._circuit_breaker_types import CircuitConfig

logger = logging.getLogger("seed_agent")


class CircuitBreakerRegistry:
    """熔断器注册表

    管理多个 Provider 的独立熔断器配置。
    """

    def __init__(self, default_config: CircuitConfig | None = None):
        self._default_config = default_config or CircuitConfig()
        self._breakers: dict[str, CircuitBreaker] = {}
        self._custom_configs: dict[str, CircuitConfig] = {}
        self._lock = asyncio.Lock()

    async def get_breaker(self, name: str) -> CircuitBreaker:
        """获取或创建熔断器"""
        async with self._lock:
            if name not in self._breakers:
                config = self._custom_configs.get(name, self._default_config)
                self._breakers[name] = CircuitBreaker(name, config)
            return self._breakers[name]

    def configure(self, name: str, config: CircuitConfig) -> None:
        """为特定 Provider 配置熔断器"""
        self._custom_configs[name] = config
        # 如果已有熔断器，更新其配置
        if name in self._breakers:
            self._breakers[name]._config = config

    async def can_execute(self, provider: str) -> bool:
        """检查 Provider 是否可执行"""
        breaker = await self.get_breaker(provider)
        return await breaker.can_execute()

    async def record_success(self, provider: str) -> None:
        """记录 Provider 成功"""
        breaker = await self.get_breaker(provider)
        await breaker.record_success()

    async def record_failure(self, provider: str) -> None:
        """记录 Provider 失败"""
        breaker = await self.get_breaker(provider)
        await breaker.record_failure()

    async def reset(self, provider: str) -> None:
        """重置 Provider 熔断器"""
        breaker = await self.get_breaker(provider)
        await breaker.reset()

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """获取所有熔断器状态"""
        return {name: breaker.get_status() for name, breaker in self._breakers.items()}

    def get_open_providers(self) -> list[str]:
        """获取所有熔断的 Provider"""
        return [
            name for name, breaker in self._breakers.items()
            if breaker.is_open
        ]


# 全局默认实例
_global_registry: CircuitBreakerRegistry | None = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """获取全局熔断器注册表"""
    global _global_registry
    if _global_registry is None:
        _global_registry = CircuitBreakerRegistry()
    return _global_registry


async def with_circuit_breaker(
    provider: str,
    operation: str,
    registry: CircuitBreakerRegistry | None = None,
) -> bool:
    """在熔断器保护下执行操作的装饰器辅助函数

    Args:
        provider: Provider 名称
        operation: 操作描述（日志）
        registry: 熔断器注册表（默认使用全局）

    Returns:
        True: 可以执行
        False: 熔断中，拒绝执行
    """
    reg = registry or get_circuit_breaker_registry()
    can_run = await reg.can_execute(provider)
    if not can_run:
        logger.warning(
            f"CircuitBreaker blocked {operation} for provider {provider}"
        )
    return can_run