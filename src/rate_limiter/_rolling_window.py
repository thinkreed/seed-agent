"""滚动窗口追踪器

滚动窗口核心机制:
- 记录每个请求的时间戳
- 滚动计算窗口内已用请求数
- 窗口为滑动窗口（非固定窗口）

性能优化:
- 使用 deque 存储时间戳，O(1) 头部删除
- 缓存最小值，避免重复 min() 调用
- 惰性清理过期记录

适用场景：
- 百炼 5 小时 6000 次限流
- 其他长窗口限流场景

时间处理：使用 time.monotonic() 计算时间差，不受系统时间调整影响
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger("seed_agent")


@dataclass
class RollingWindowState:
    """滚动窗口状态（用于持久化）"""

    requests: list[float]  # 时间戳列表
    total_requests_lifetime: int = 0


class RollingWindowTracker:
    """滚动窗口追踪器

    核心机制:
    - 记录每个请求的时间戳
    - 滚动计算窗口内已用请求数
    - 窗口为滑动窗口（非固定窗口）

    性能优化:
    - 使用 deque 存储时间戳，O(1) 头部删除
    - 缓存最小值，避免重复 min() 调用
    - 惰性清理过期记录

    适用场景：
    - 百炼 5 小时 6000 次限流
    - 其他长窗口限流场景
    """

    def __init__(self, window_limit: int, window_duration: float):
        """
        Args:
            window_limit: 窗口内最大请求数
            window_duration: 窗口时长（秒）
        """
        self.window_limit = window_limit
        self.window_duration = window_duration
        self.requests: deque[float] = deque()  # 使用 deque 优化头部删除
        self.total_requests_lifetime = 0
        self._lock = asyncio.Lock()

        # 缓存：最小时间戳（避免重复 min() 调用）
        self._min_timestamp: float | None = None
        # 缓存：上次清理时间（惰性清理）
        self._last_cleanup_time: float = 0.0

    def _clean_expired(self, now: float) -> None:
        """清理过期记录（内部方法，需在锁内调用）

        性能优化：使用 deque 的 popleft() 实现 O(1) 头部删除
        """
        # 惰性清理：仅在需要时清理（窗口接近满或超过清理间隔）
        cleanup_interval = self.window_duration / 10  # 每 1/10 窗口清理一次

        if (
            now - self._last_cleanup_time < cleanup_interval
            and len(self.requests) < self.window_limit * 0.8
        ):
            return  # 不需要清理

        self._last_cleanup_time = now

        # 使用 deque 高效清理过期记录（从头部删除）
        cutoff = now - self.window_duration
        while self.requests and self.requests[0] < cutoff:
            self.requests.popleft()

        # 更新最小值缓存
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
            now = time.monotonic()  # 使用 monotonic 避免系统时间调整影响
            self._clean_expired(now)

            if len(self.requests) < self.window_limit:
                return True, 0.0

            # 窗口满了，计算等待时间（使用缓存的 min 值）
            oldest = self._min_timestamp or self.requests[0]
            wait_until = oldest + self.window_duration
            wait_seconds = wait_until - now

            return False, max(0.0, wait_seconds)

    async def record_request(self) -> None:
        """记录一个请求"""
        async with self._lock:
            now = time.monotonic()  # 使用 monotonic 避免系统时间调整影响
            self.requests.append(now)
            self.total_requests_lifetime += 1

            # 更新缓存（新请求时间戳肯定大于等于当前最小值）
            if self._min_timestamp is None:
                self._min_timestamp = now

    def get_remaining(self) -> int:
        """获取窗口内剩余请求数（同步版本，用于快速查询）

        注意：此方法不清理过期记录，结果可能略有偏差
        """
        now = time.monotonic()  # 使用 monotonic 避免系统时间调整影响
        cutoff = now - self.window_duration

        # 快速估算：使用缓存或遍历
        if self._min_timestamp is None or self._min_timestamp >= cutoff:
            # 所有请求都有效（或无请求）
            active_count = len(self.requests)
        else:
            # 需要精确计算（较少情况）
            active_count = sum(1 for t in self.requests if t >= cutoff)

        return max(0, self.window_limit - active_count)

    def get_reset_time(self) -> float:
        """获取窗口重置时间（最早请求过期时间）

        注意：返回的是 monotonic 时间戳，用于计算等待时间
        """
        if not self.requests:
            return time.monotonic()  # 使用 monotonic 避免系统时间调整影响
        # 使用缓存的最小值
        return (self._min_timestamp or self.requests[0]) + self.window_duration

    def get_usage_ratio(self) -> float:
        """获取窗口使用率（0.0 - 1.0）

        注意：此方法不清理过期记录，结果可能略有偏差
        """
        if self.window_limit == 0:
            return 1.0

        now = time.monotonic()  # 使用 monotonic 避免系统时间调整影响
        cutoff = now - self.window_duration

        # 快速估算
        if self._min_timestamp is None or self._min_timestamp >= cutoff:
            active_count = len(self.requests)
        else:
            active_count = sum(1 for t in self.requests if t >= cutoff)

        return min(1.0, active_count / self.window_limit)

    def get_state(self) -> RollingWindowState:
        """获取当前状态（用于持久化）

        注意：持久化时转换为 wall clock 时间（time.time()），
        便于外部理解和调试。恢复时需要考虑时间差调整。
        """
        # 将 monotonic 时间转换为 wall clock 时间用于持久化
        now_monotonic = time.monotonic()
        now_wall = time.time()
        offset = now_wall - now_monotonic  # monotonic 与 wall clock 的偏移

        return RollingWindowState(
            requests=[t + offset for t in self.requests],  # 转换为 wall clock 时间
            total_requests_lifetime=self.total_requests_lifetime,
        )

    def restore_state(self, state: RollingWindowState) -> None:
        """恢复状态（从持久化）

        注意：从 wall clock 时间转换为 monotonic 时间，
        只恢复未过期的请求。
        """
        now_monotonic = time.monotonic()
        now_wall = time.time()
        offset = now_monotonic - now_wall  # wall clock 与 monotonic 的偏移

        cutoff = now_monotonic - self.window_duration

        # 将 wall clock 时间转换为 monotonic 时间，并过滤过期请求
        self.requests = deque(
            t + offset for t in state.requests if t + offset >= cutoff
        )
        self.total_requests_lifetime = state.total_requests_lifetime

        # 更新缓存
        if self.requests:
            self._min_timestamp = self.requests[0]
        else:
            self._min_timestamp = None