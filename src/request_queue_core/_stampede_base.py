"""
Stampede Protection 基类

包含缓存管理和统计方法。
"""

import asyncio
import time
from typing import Any, Generic, TypeVar

from ._stampede_types import StampedeConfig, StampedeEntry, StampedeStats

T = TypeVar("T")


class StampedeProtectionBase(Generic[T]):
    """Stampede Protection 基类

    提供缓存管理和统计功能。
    """

    def __init__(self, config: StampedeConfig | None = None):
        self._config = config or StampedeConfig()
        self._entries: dict[str, StampedeEntry[T]] = {}
        self._lock = asyncio.Lock()
        self._stats = StampedeStats()

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