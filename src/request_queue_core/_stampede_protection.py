"""
Stampede Protection 核心实现

并发缓存击穿保护机制，防止缓存失效时大量请求同时穿透到后端服务。
"""

import asyncio
import logging
import time
from typing import Generic, TypeVar

from ._stampede_base import StampedeProtectionBase
from ._stampede_types import StampedeConfig, StampedeEntry

logger = logging.getLogger("seed_agent")

T = TypeVar("T")


class StampedeProtection(StampedeProtectionBase[T], Generic[T]):
    """并发缓存击穿保护

    防止缓存失效时大量请求同时穿透到后端服务。
    """

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
            return await self._execute_refresh(entry, refresh_fn, key)
        else:
            return await self._wait_for_refresh(entry, key)

    async def _execute_refresh(
        self,
        entry: StampedeEntry[T],
        refresh_fn: callable,
        key: str,
    ) -> T:
        """执行刷新（持有锁）"""
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

    async def _wait_for_refresh(self, entry: StampedeEntry[T], key: str) -> T:
        """等待刷新完成"""
        self._stats.shared_requests += 1

        try:
            await asyncio.wait_for(
                self._wait_for_result(entry),
                timeout=self._config.wait_timeout,
            )
        except TimeoutError:
            self._stats.timeout_requests += 1
            raise TimeoutError(f"Stampede: timeout waiting for key={key}")

        # 返回结果或错误
        if entry.error:
            raise entry.error
        if entry.result is not None:
            return entry.result

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