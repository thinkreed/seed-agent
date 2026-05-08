"""
Stampede Protection 模块

借鉴 worldmonitor-architecture 设计的并发缓存击穿保护机制。

核心功能:
- 单个请求实际调用 API，其他等待
- 自动过期和刷新
- 统计和监控

适用场景:
- 缓存失效时的请求合并
- 并发相同查询的合并
- 资源加载的防重
"""

import asyncio
from typing import Any

from ._stampede_base import StampedeProtectionBase
from ._stampede_protection import StampedeProtection
from ._stampede_types import StampedeConfig, StampedeEntry, StampedeStats

__all__ = [
    "StampedeConfig",
    "StampedeEntry",
    "StampedeStats",
    "StampedeProtection",
    "StampedeProtectionBase",
    "StampedeRegistry",
    "get_stampede_registry",
    "with_stampede_protection",
]


class StampedeRegistry:
    """Stampede Protection 注册表

    管理多个 Stampede 实例，按类型或域分组。
    """

    def __init__(self):
        self._protections: dict[str, StampedeProtection[Any]] = {}
        self._lock = asyncio.Lock()

    async def get_protection(self, domain: str) -> StampedeProtection[Any]:
        """获取或创建域的 Stampede 实例"""
        async with self._lock:
            if domain not in self._protections:
                self._protections[domain] = StampedeProtection[Any]()
            return self._protections[domain]

    async def invalidate_domain(self, domain: str) -> None:
        """失效整个域"""
        protection = self._protections.get(domain)
        if protection:
            await protection.invalidate_all()

    def get_all_stats(self) -> dict[str, dict[str, Any]]:
        """获取所有域统计"""
        return {
            domain: protection.get_stats()
            for domain, protection in self._protections.items()
        }


# 全局默认实例
_global_registry: StampedeRegistry | None = None


def get_stampede_registry() -> StampedeRegistry:
    """获取全局 Stampede 注册表"""
    global _global_registry
    if _global_registry is None:
        _global_registry = StampedeRegistry()
    return _global_registry


async def with_stampede_protection(
    domain: str,
    key: str,
    refresh_fn: callable,
    force_refresh: bool = False,
) -> Any:
    """在 Stampede 保护下执行刷新

    Args:
        domain: 域名称（如 "llm_cache", "memory_search"）
        key: 缓存键
        refresh_fn: 刷新函数
        force_refresh: 强制刷新

    Returns:
        刷新结果
    """
    registry = get_stampede_registry()
    protection = await registry.get_protection(domain)
    return await protection.get_or_refresh(key, refresh_fn, force_refresh)