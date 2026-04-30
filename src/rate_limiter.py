"""LLM 请求限流器

包含两个核心组件:
- TokenBucket: 令牌桶限流器，平滑突发请求
- RollingWindowTracker: 滚动窗口追踪器，精确控制窗口内请求数
"""

import time
import asyncio
import logging
from typing import Tuple
from dataclasses import dataclass

logger = logging.getLogger("seed_agent")


@dataclass
class TokenBucketState:
    """Token Bucket 状态（用于持久化）"""
    tokens: float
    last_refill_time: float


class TokenBucket:
    """Token Bucket 限流器

    核心算法:
    - tokens 以固定速率补充
    - 每次请求消耗 1 token
    - tokens 不能超过 capacity
    - tokens 不足时需要等待

    线程安全：使用 asyncio.Lock 保证并发安全
    """

    def __init__(self, rate: float, capacity: float, initial_tokens: float | None = None):
        """
        Args:
            rate: 每秒补充的 token 数
            capacity: 最大 token 容量
            initial_tokens: 初始 token 数，默认满载
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = initial_tokens if initial_tokens is not None else capacity
        self.last_refill = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> Tuple[bool, float]:
        """尝试获取 token

        Args:
            tokens: 需要获取的 token 数

        Returns:
            (allowed, wait_time): 是否允许, 需等待时间
        """
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_refill

            # 补充 tokens
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_refill = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True, 0.0

            # 需要等待
            wait_time = (tokens - self.tokens) / self.rate
            return False, wait_time

    async def wait_and_acquire(self, tokens: int = 1, max_wait: float = 60.0) -> bool:
        """等待并获取 token

        Args:
            tokens: 需要获取的 token 数
            max_wait: 最大等待时间（秒）

        Returns:
            是否成功获取
        """
        start = time.time()
        while True:
            allowed, wait_time = await self.acquire(tokens)
            if allowed:
                return True

            elapsed = time.time() - start
            if elapsed + wait_time > max_wait:
                logger.warning(f"Token bucket wait timeout: {elapsed + wait_time:.1f}s > {max_wait}s")
                return False

            await asyncio.sleep(wait_time)

    def get_state(self) -> TokenBucketState:
        """获取当前状态（用于持久化）"""
        return TokenBucketState(
            tokens=self.tokens,
            last_refill_time=self.last_refill
        )

    def restore_state(self, state: TokenBucketState) -> None:
        """恢复状态（从持久化）"""
        self.tokens = state.tokens
        self.last_refill = state.last_refill_time


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
        self.requests: list[float] = []
        self.total_requests_lifetime = 0
        self._lock = asyncio.Lock()

    async def check_available(self) -> Tuple[bool, float]:
        """检查是否可以发起请求

        Returns:
            (available, wait_seconds)
        """
        async with self._lock:
            now = time.time()

            # 清理过期记录
            self.requests = [
                t for t in self.requests
                if now - t < self.window_duration
            ]

            if len(self.requests) < self.window_limit:
                return True, 0.0

            # 窗口满了，计算等待时间
            oldest = min(self.requests)
            wait_until = oldest + self.window_duration
            wait_seconds = wait_until - now

            return False, max(0.0, wait_seconds)

    async def record_request(self) -> None:
        """记录一个请求"""
        async with self._lock:
            self.requests.append(time.time())
            self.total_requests_lifetime += 1

    def get_remaining(self) -> int:
        """获取窗口内剩余请求数"""
        now = time.time()
        active = [t for t in self.requests if now - t < self.window_duration]
        return max(0, self.window_limit - len(active))

    def get_reset_time(self) -> float:
        """获取窗口重置时间（最早请求过期时间）"""
        if not self.requests:
            return time.time()
        return min(self.requests) + self.window_duration

    def get_usage_ratio(self) -> float:
        """获取窗口使用率（0.0 - 1.0）"""
        now = time.time()
        active = [t for t in self.requests if now - t < self.window_duration]
        return len(active) / self.window_limit

    def get_state(self) -> RollingWindowState:
        """获取当前状态（用于持久化）"""
        return RollingWindowState(
            requests=list(self.requests),
            total_requests_lifetime=self.total_requests_lifetime
        )

    def restore_state(self, state: RollingWindowState) -> None:
        """恢复状态（从持久化）"""
        now = time.time()
        # 只恢复未过期的请求
        self.requests = [
            t for t in state.requests
            if now - t < self.window_duration
        ]
        self.total_requests_lifetime = state.total_requests_lifetime


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

    async def acquire(self) -> Tuple[bool, float]:
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
        start = time.time()
        while True:
            allowed, wait_time = await self.acquire()
            if allowed:
                # 记录请求
                await self.window_tracker.record_request()
                return True

            elapsed = time.time() - start
            if elapsed + wait_time > max_wait:
                logger.warning(f"Rate limiter wait timeout: {elapsed + wait_time:.1f}s > {max_wait}s")
                return False

            await asyncio.sleep(wait_time)

    def get_status(self) -> RateLimitStatus:
        """获取限流状态快照"""
        bucket_state = self.token_bucket.get_state()
        window_state = self.window_tracker.get_state()

        now = time.time()
        active_requests = [
            t for t in window_state.requests
            if now - t < self.window_tracker.window_duration
        ]

        return RateLimitStatus(
            tokens_available=bucket_state.tokens,
            token_bucket_capacity=self.token_bucket.capacity,
            refill_rate=self.token_bucket.rate,
            window_requests_used=len(active_requests),
            window_requests_remaining=self.window_tracker.get_remaining(),
            window_requests_limit=self.window_tracker.window_limit,
            window_reset_time=self.window_tracker.get_reset_time(),
            window_usage_ratio=self.window_tracker.get_usage_ratio(),
            total_requests_lifetime=window_state.total_requests_lifetime,
        )

    def get_state(self) -> Tuple[TokenBucketState, RollingWindowState]:
        """获取完整状态（用于持久化）"""
        return (
            self.token_bucket.get_state(),
            self.window_tracker.get_state()
        )

    def restore_state(
        self,
        bucket_state: TokenBucketState | None = None,
        window_state: RollingWindowState | None = None
    ) -> None:
        """恢复状态（从持久化）"""
        if bucket_state:
            self.token_bucket.restore_state(bucket_state)
        if window_state:
            self.window_tracker.restore_state(window_state)