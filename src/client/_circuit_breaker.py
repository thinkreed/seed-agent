"""
Circuit Breaker 模块

状态流转:
Closed -> Open (连续失败达到阈值)
Open -> HalfOpen (冷却时间结束)
HalfOpen -> Closed (探测成功)
HalfOpen -> Open (探测失败)
"""

import asyncio
import logging
import time
from typing import Any

from ._circuit_breaker_types import CircuitConfig, CircuitState, CircuitStats

logger = logging.getLogger("seed_agent")


class CircuitBreaker:
    """单个 Provider 的熔断器

    状态机: Closed(正常) -> Open(熔断) -> HalfOpen(探测)
    并发安全：使用 asyncio.Lock 保护状态变更
    """

    def __init__(self, name: str, config: CircuitConfig | None = None):
        self.name = name
        self._config = config or CircuitConfig()
        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._lock = asyncio.Lock()
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def stats(self) -> CircuitStats:
        return self._stats

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED

    @property
    def is_half_open(self) -> bool:
        return self._state == CircuitState.HALF_OPEN

    async def can_execute(self) -> bool:
        """检查是否可以执行请求"""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                elapsed = time.time() - self._stats.last_failure_time
                if elapsed >= self._config.recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
                    self._half_open_calls = 0
                    logger.info(
                        f"CircuitBreaker[{self.name}] HALF_OPEN after {elapsed:.1f}s"
                    )
                    return True
                self._stats.total_rejections += 1
                return False

            # HALF_OPEN: 限制探测次数
            if self._half_open_calls < self._config.half_open_max_calls:
                self._half_open_calls += 1
                return True
            self._stats.total_rejections += 1
            return False

    async def record_success(self) -> None:
        """记录成功"""
        async with self._lock:
            self._stats.success_count += 1
            self._stats.total_successes += 1
            self._stats.failure_count = 0

            if self._state == CircuitState.HALF_OPEN:
                if self._stats.success_count >= self._config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                    logger.info(f"CircuitBreaker[{self.name}] recovered to CLOSED")

    async def record_failure(self) -> None:
        """记录失败"""
        async with self._lock:
            self._stats.failure_count += 1
            self._stats.total_failures += 1
            self._stats.last_failure_time = time.time()
            self._stats.success_count = 0

            if self._state == CircuitState.CLOSED:
                if self._stats.failure_count >= self._config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
                    logger.warning(
                        f"CircuitBreaker[{self.name}] OPEN after "
                        f"{self._stats.failure_count} failures"
                    )
            elif self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
                logger.warning(f"CircuitBreaker[{self.name}] probe failed, back to OPEN")

    def _transition_to(self, new_state: CircuitState) -> None:
        self._state = new_state
        self._stats.last_state_change = time.time()

    async def reset(self) -> None:
        """强制重置"""
        async with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._stats.failure_count = 0
            self._stats.success_count = 0
            self._half_open_calls = 0
            logger.info(f"CircuitBreaker[{self.name}] reset to CLOSED")

    def get_status(self) -> dict[str, Any]:
        """获取状态摘要"""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._stats.failure_count,
            "success_count": self._stats.success_count,
            "total_failures": self._stats.total_failures,
            "total_successes": self._stats.total_successes,
            "total_rejections": self._stats.total_rejections,
            "last_failure_time": self._stats.last_failure_time,
            "last_state_change": self._stats.last_state_change,
        }