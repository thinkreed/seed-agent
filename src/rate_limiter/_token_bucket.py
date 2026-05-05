"""令牌桶限流器

Token Bucket 核心算法:
- tokens 以固定速率补充
- 每次请求消耗 1 token
- tokens 不能超过 capacity
- tokens 不足时需要等待

线程安全：使用 asyncio.Lock 保证并发安全

时间处理：使用 time.monotonic() 计算时间差，不受系统时间调整影响
"""

import asyncio
import logging
import time
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

    def __init__(
        self, rate: float, capacity: float, initial_tokens: float | None = None
    ):
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
                logger.warning(
                    f"Token bucket wait timeout: {elapsed + wait_time:.1f}s > {max_wait}s"
                )
                return False

            await asyncio.sleep(wait_time)

    def get_state(self) -> TokenBucketState:
        """获取当前状态（用于持久化）"""
        return TokenBucketState(tokens=self.tokens, last_refill_time=self.last_refill)

    def restore_state(self, state: TokenBucketState) -> None:
        """恢复状态（从持久化）"""
        self.tokens = state.tokens
        self.last_refill = state.last_refill_time