"""LLM 请求限流器

包含两个核心组件:
- TokenBucket: 令牌桶限流器，平滑突发请求
- RollingWindowTracker: 滚动窗口追踪器，精确控制窗口内请求数

性能优化:
- TokenBucket: 抽取 refill 方法减少重复计算
- RollingWindowTracker: 缓存 min 值、批量清理、惰性过期检查

时间处理:
- 使用 time.monotonic() 计算时间差，不受系统时间调整影响
- 持久化使用 time.time()，便于外部理解和调试
"""

import asyncio
import logging
import time
from collections import deque
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
        self.last_refill = time.monotonic()  # 使用 monotonic 避免系统时间调整影响
        self._lock = asyncio.Lock()

    def _refill(self, now: float) -> None:
        """补充 tokens（内部方法，需在锁内调用）"""
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

    async def acquire(self, tokens: int = 1) -> tuple[bool, float]:
        """尝试获取 token

        Args:
            tokens: 需要获取的 token 数

        Returns:
            (allowed, wait_time): 是否允许, 需等待时间
        """
        async with self._lock:
            now = time.monotonic()  # 使用 monotonic 避免系统时间调整影响
            self._refill(now)

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
        start = time.monotonic()  # 使用 monotonic 避免系统时间调整影响
        while True:
            allowed, wait_time = await self.acquire(tokens)
            if allowed:
                return True

            elapsed = time.monotonic() - start  # 使用 monotonic 避免系统时间调整影响
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

        if now - self._last_cleanup_time < cleanup_interval and len(self.requests) < self.window_limit * 0.8:
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
            total_requests_lifetime=self.total_requests_lifetime
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
        self.requests = deque(t + offset for t in state.requests if t + offset >= cutoff)
        self.total_requests_lifetime = state.total_requests_lifetime

        # 更新缓存
        if self.requests:
            self._min_timestamp = self.requests[0]
        else:
            self._min_timestamp = None


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
                logger.warning(f"Rate limiter wait timeout: {elapsed + wait_time:.1f}s > {max_wait}s")
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
