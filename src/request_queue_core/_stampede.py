"""
Stampede Protection 模块

借鉴 worldmonitor-architecture 设计的并发缓存击穿保护机制。

核心功能:
- 单个请求实际调用 API，其他等待
- 自动过期和刷新
- 统计和监控

参考 worldmonitor:
- Stampede Protection: 单个请求实际调用 API，其他等待
- 避免缓存失效时大量请求穿透到后端

实现原理:
1. 第一个请求获取 "刷新锁"，执行实际调用
2. 其他请求等待第一个请求完成
3. 第一个请求完成后，所有等待者共享结果
4. 如果第一个请求失败，下一个等待者获得刷新机会

适用场景:
- 缓存失效时的请求合并
- 并发相同查询的合并
- 资源加载的防重
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

logger = logging.getLogger("seed_agent")

T = TypeVar("T")


@dataclass
class StampedeConfig:
    """Stampede Protection 配置"""
    wait_timeout: float = 30.0       # 等待刷新的最大时间
    result_ttl: float = 60.0         # 结果缓存时间
    max_waiters: int = 100           # 最大等待者数量


@dataclass
class StampedeEntry(Generic[T]):
    """Stampede 条目"""
    key: str
    refresh_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    is_refreshing: bool = False
    result: T | None = None
    result_time: float = 0.0
    error: Exception | None = None
    waiter_count: int = 0
    refresh_task: asyncio.Task[T] | None = None


@dataclass
class StampedeStats:
    """Stampede 统计"""
    total_requests: int = 0
    refresh_requests: int = 0      # 实际执行刷新的请求
    shared_requests: int = 0       # 共享结果的请求
    timeout_requests: int = 0      # 等待超时的请求
    error_requests: int = 0        # 刷新失败的请求
    cache_hits: int = 0            # 直接缓存命中


class StampedeProtection(Generic[T]):
    """并发缓存击穿保护

    防止缓存失效时大量请求同时穿透到后端服务。

    使用方式:
    ```python
    stampede = StampedeProtection[str]()

    async def get_data(key: str):
        async def refresh():
            return await fetch_from_backend(key)

        result = await stampede.get_or_refresh(key, refresh)
        return result
    ```

    并发安全：使用 asyncio.Lock 保护刷新状态
    """

    def __init__(
        self,
        config: StampedeConfig | None = None,
    ):
        self._config = config or StampedeConfig()
        self._entries: dict[str, StampedeEntry[T]] = {}
        self._lock = asyncio.Lock()
        self._stats = StampedeStats()

    async def get_or_refresh(
        self,
        key: str,
        refresh_fn: callable,
        force_refresh: bool = False,
    ) -> T:
        """获取结果或触发刷新

        Args:
            key: 缓存键
            refresh_fn: 刷新函数（异步）
            force_refresh: 强制刷新（忽略缓存）

        Returns:
            刷新结果

        Raises:
            asyncio.TimeoutError: 等待超时
            Exception: 刷新失败
        """
        self._stats.total_requests += 1

        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = StampedeEntry[T](key=key)
                self._entries[key] = entry

        # 检查缓存是否有效
        now = time.time()
        if not force_refresh and entry.result is not None:
            if now - entry.result_time < self._config.result_ttl:
                self._stats.cache_hits += 1
                return entry.result

        # 尝试获取刷新锁
        acquired = await asyncio.wait_for(
            entry.refresh_lock.acquire(),
            timeout=self._config.wait_timeout,
        )

        if acquired:
            # 获得刷新锁：执行刷新
            try:
                entry.is_refreshing = True
                self._stats.refresh_requests += 1

                if self._config.result_ttl > 0:
                    logger.debug(f"Stampede: refreshing key={key}")

                result = await refresh_fn()

                # 更新缓存
                async with self._lock:
                    entry.result = result
                    entry.result_time = time.time()
                    entry.error = None
                    entry.is_refreshing = False

                return result

            except Exception as e:
                async with self._lock:
                    entry.error = e
                    entry.is_refreshing = False
                self._stats.error_requests += 1
                raise

            finally:
                entry.refresh_lock.release()

        else:
            # 未获得刷新锁：等待结果
            self._stats.shared_requests += 1

            # 等待刷新完成
            try:
                await asyncio.wait_for(
                    self._wait_for_result(entry),
                    timeout=self._config.wait_timeout,
                )
            except TimeoutError:
                self._stats.timeout_requests += 1
                raise TimeoutError(
                    f"Stampede: timeout waiting for key={key}"
                )

            # 返回结果或错误
            if entry.error:
                raise entry.error
            if entry.result is not None:
                return entry.result

            # 刷新成功但没有结果（异常情况）
            raise RuntimeError(f"Stampede: no result for key={key}")

    async def _wait_for_result(self, entry: StampedeEntry[T]) -> None:
        """等待刷新完成"""
        entry.waiter_count += 1
        try:
            while entry.is_refreshing:
                await asyncio.sleep(0.1)
                if entry.waiter_count > self._config.max_waiters:
                    logger.warning(
                        f"Stampede: too many waiters for key={entry.key}, "
                        f"count={entry.waiter_count}"
                    )
                    break
        finally:
            entry.waiter_count -= 1

    async def invalidate(self, key: str) -> None:
        """失效缓存条目"""
        async with self._lock:
            entry = self._entries.get(key)
            if entry:
                entry.result = None
                entry.result_time = 0.0
                entry.error = None

    async def invalidate_all(self) -> None:
        """失效所有缓存"""
        async with self._lock:
            for entry in self._entries.values():
                entry.result = None
                entry.result_time = 0.0
                entry.error = None

    async def remove(self, key: str) -> None:
        """移除缓存条目"""
        async with self._lock:
            self._entries.pop(key, None)

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        return {
            "total_requests": self._stats.total_requests,
            "refresh_requests": self._stats.refresh_requests,
            "shared_requests": self._stats.shared_requests,
            "cache_hits": self._stats.cache_hits,
            "timeout_requests": self._stats.timeout_requests,
            "error_requests": self._stats.error_requests,
            "efficiency_ratio": (
                self._stats.shared_requests / self._stats.refresh_requests
                if self._stats.refresh_requests > 0 else 0.0
            ),
            "active_entries": len(self._entries),
        }

    def get_entry_status(self, key: str) -> dict[str, Any] | None:
        """获取单个条目状态"""
        entry = self._entries.get(key)
        if not entry:
            return None
        return {
            "key": entry.key,
            "is_refreshing": entry.is_refreshing,
            "has_result": entry.result is not None,
            "result_age": time.time() - entry.result_time if entry.result else 0.0,
            "waiter_count": entry.waiter_count,
            "has_error": entry.error is not None,
        }


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