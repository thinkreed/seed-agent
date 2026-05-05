"""组合限流器

组合 Token Bucket + Rolling Window 的双重限流机制:
- Token Bucket: 平滑突发请求
- Rolling Window: 控制长周期窗口内的总请求数
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from src.rate_limiter._rolling_window import RollingWindowState, RollingWindowTracker
from src.rate_limiter._token_bucket import TokenBucket, TokenBucketState

logger = logging.getLogger("seed_agent")


@dataclass
class RateLimitStatus:
    """限流状态快照"""

    # Token Bucket 状态
    tokens_available: float
    token_bucket_capacity: float
    refill_rate: float

    # 滚动窗口状态
    window_requests_used: int
    window_requests_remaining: int
    window_requests_limit: int
    window_reset_time: float
    window_usage_ratio: float

    # 统计信息
    total_requests_lifetime: int


class RateLimiter:
    """组合限流器

    组合 Token Bucket + Rolling Window 的双重限流机制:
    - Token Bucket: 平滑突发请求
    - Rolling Window: 控制长周期窗口内的总请求数
    """

    def __init__(
        self,
        rate: float,
        capacity: float,
        window_limit: int,
        window_duration: float,
    ):
        """
        Args:
            rate: Token 补充速率（requests/sec）
            capacity: Token 桶容量
            window_limit: 滚动窗口请求上限
            window_duration: 滚动窗口时长（秒）
        """
        self.token_bucket = TokenBucket(rate, capacity)
        self.window_tracker = RollingWindowTracker(window_limit, window_duration)

    async def acquire(self) -> tuple[bool, float]:
        """尝试获取请求许可

        Returns:
            (allowed, wait_time): 是否允许, 需等待时间
        """
        # 先检查滚动窗口（硬限制）
        window_allowed, window_wait = await self.window_tracker.check_available()
        if not window_allowed:
            logger.info(f"Rolling window limit reached, wait {window_wait:.1f}s")
            return False, window_wait

        # 再检查 Token Bucket（软限制，平滑突发）
        bucket_allowed, bucket_wait = await self.token_bucket.acquire()
        if not bucket_allowed:
            logger.debug(f"Token bucket empty, wait {bucket_wait:.1f}s")
            return False, bucket_wait

        return True, 0.0

    async def wait_and_acquire(self, max_wait: float = 60.0) -> bool:
        """等待并获取请求许可

        Args:
            max_wait: 最大等待时间（秒）

        Returns:
            是否成功获取
        """
        start = time.monotonic()  # 使用 monotonic 避免系统时间调整影响
        while True:
            allowed, wait_time = await self.acquire()
            if allowed:
                # 记录请求
                await self.window_tracker.record_request()
                return True

            elapsed = time.monotonic() - start  # 使用 monotonic 避免系统时间调整影响
            if elapsed + wait_time > max_wait:
                logger.warning(
                    f"Rate limiter wait timeout: {elapsed + wait_time:.1f}s > {max_wait}s"
                )
                return False

            await asyncio.sleep(wait_time)

    def get_status(self) -> RateLimitStatus:
        """获取限流状态快照"""
        bucket_state = self.token_bucket.get_state()
        window_state = self.window_tracker.get_state()

        # 使用 wall clock 时间显示（便于人类理解）
        now_wall = time.time()
        now_monotonic = time.monotonic()
        offset = now_wall - now_monotonic

        cutoff = now_monotonic - self.window_tracker.window_duration
        # window_state.requests 已经是 wall clock 时间
        # 需要转换为 monotonic 进行比较
        active_requests = sum(1 for t in window_state.requests if t - offset >= cutoff)

        return RateLimitStatus(
            tokens_available=bucket_state.tokens,
            token_bucket_capacity=self.token_bucket.capacity,
            refill_rate=self.token_bucket.rate,
            window_requests_used=active_requests,
            window_requests_remaining=self.window_tracker.get_remaining(),
            window_requests_limit=self.window_tracker.window_limit,
            window_reset_time=self.window_tracker.get_reset_time(),
            window_usage_ratio=self.window_tracker.get_usage_ratio(),
            total_requests_lifetime=window_state.total_requests_lifetime,
        )

    def get_state(self) -> tuple[TokenBucketState, RollingWindowState]:
        """获取完整状态（用于持久化）"""
        return (self.token_bucket.get_state(), self.window_tracker.get_state())

    def restore_state(
        self,
        bucket_state: TokenBucketState | None = None,
        window_state: RollingWindowState | None = None,
    ) -> None:
        """恢复状态（从持久化）"""
        if bucket_state:
            self.token_bucket.restore_state(bucket_state)
        if window_state:
            self.window_tracker.restore_state(window_state)