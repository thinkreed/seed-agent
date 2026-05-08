"""滚动窗口追踪器

核心机制:
- 记录每个请求的时间戳
- 滚动计算窗口内已用请求数
- 窗口为滑动窗口（非固定窗口）

性能优化:
- 使用 deque 存储时间戳，O(1) 头部删除
- 缓存最小值，避免重复 min() 调用
- 惰性清理过期记录
"""

import asyncio
import logging
import time
from collections import deque

from src.rate_limiter._rolling_window_types import RollingWindowState

logger = logging.getLogger("seed_agent")


class RollingWindowTracker:
    """滚动窗口追踪器"""

    def __init__(self, window_limit: int, window_duration: float):
        """
        Args:
            window_limit: 窗口内最大请求数
            window_duration: 窗口时长（秒）
        """
        self.window_limit = window_limit
        self.window_duration = window_duration
        self.requests: deque[float] = deque()
        self.total_requests_lifetime = 0
        self._lock = asyncio.Lock()

        # 缓存：最小时间戳
        self._min_timestamp: float | None = None
        # 缓存：上次清理时间
        self._last_cleanup_time: float = 0.0

    def _clean_expired(self, now: float) -> None:
        """清理过期记录（内部方法，需在锁内调用）"""
        cleanup_interval = self.window_duration / 10

        if (
            now - self._last_cleanup_time < cleanup_interval
            and len(self.requests) < self.window_limit * 0.8
        ):
            return

        self._last_cleanup_time = now

        cutoff = now - self.window_duration
        while self.requests and self.requests[0] < cutoff:
            self.requests.popleft()

        if self.requests:
            self._min_timestamp = self.requests[0]
        else:
            self._min_timestamp = None

    async def check_available(self) -> tuple[bool, float]:
        """检查是否可以发起请求

        Returns:
            (available, wait_seconds)
        """
        async with self._lock:
            now = time.monotonic()
            self._clean_expired(now)

            if len(self.requests) < self.window_limit:
                return True, 0.0

            oldest = self._min_timestamp or self.requests[0]
            wait_until = oldest + self.window_duration
            wait_seconds = wait_until - now

            return False, max(0.0, wait_seconds)

    async def record_request(self) -> None:
        """记录一个请求"""
        async with self._lock:
            now = time.monotonic()
            self.requests.append(now)
            self.total_requests_lifetime += 1

            if self._min_timestamp is None:
                self._min_timestamp = now

    def get_remaining(self) -> int:
        """获取窗口内剩余请求数"""
        now = time.monotonic()
        cutoff = now - self.window_duration

        if self._min_timestamp is None or self._min_timestamp >= cutoff:
            active_count = len(self.requests)
        else:
            active_count = sum(1 for t in self.requests if t >= cutoff)

        return max(0, self.window_limit - active_count)

    def get_reset_time(self) -> float:
        """获取窗口重置时间"""
        if not self.requests:
            return time.monotonic()
        return (self._min_timestamp or self.requests[0]) + self.window_duration

    def get_usage_ratio(self) -> float:
        """获取窗口使用率（0.0 - 1.0）"""
        if self.window_limit == 0:
            return 1.0

        now = time.monotonic()
        cutoff = now - self.window_duration

        if self._min_timestamp is None or self._min_timestamp >= cutoff:
            active_count = len(self.requests)
        else:
            active_count = sum(1 for t in self.requests if t >= cutoff)

        return min(1.0, active_count / self.window_limit)

    def get_state(self) -> RollingWindowState:
        """获取当前状态（用于持久化）"""
        now_monotonic = time.monotonic()
        now_wall = time.time()
        offset = now_wall - now_monotonic

        return RollingWindowState(
            requests=[t + offset for t in self.requests],
            total_requests_lifetime=self.total_requests_lifetime,
        )

    def restore_state(self, state: RollingWindowState) -> None:
        """恢复状态（从持久化）"""
        now_monotonic = time.monotonic()
        now_wall = time.time()
        offset = now_monotonic - now_wall

        cutoff = now_monotonic - self.window_duration

        self.requests = deque(
            t + offset for t in state.requests if t + offset >= cutoff
        )
        self.total_requests_lifetime = state.total_requests_lifetime

        if self.requests:
            self._min_timestamp = self.requests[0]
        else:
            self._min_timestamp = None


__all__ = ["RollingWindowTracker"]