"""
Circuit Breaker 模块

借鉴 claude-mem 和 worldmonitor-architecture 设计的熔断器机制。

核心功能:
- 连续失败计数触发熔断
- 自动恢复探测（半开状态）
- 独立的 Provider 熔断配置

状态流转:
Closed -> Open (连续失败达到阈值)
Open -> HalfOpen (冷却时间结束)
HalfOpen -> Closed (探测成功)
HalfOpen -> Open (探测失败)

参考:
- claude-mem: 连续重启 3 次触发备用 Provider
- worldmonitor: 每个数据域独立熔断配置
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("seed_agent")


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"  # 正常状态
    OPEN = "open"      # 熔断状态（拒绝请求）
    HALF_OPEN = "half_open"  # 半开状态（探测恢复）


@dataclass
class CircuitConfig:
    """熔断器配置"""
    failure_threshold: int = 3       # 连续失败次数触发熔断
    recovery_timeout: float = 30.0   # 熔断后等待恢复的秒数
    half_open_max_calls: int = 1     # 半开状态最大探测次数
    success_threshold: int = 2       # 半开状态成功次数恢复正常


@dataclass
class CircuitStats:
    """熔断器统计"""
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_state_change: float = 0.0
    total_failures: int = 0
    total_successes: int = 0
    total_rejections: int = 0


class CircuitBreaker:
    """单个 Provider 的熔断器

    状态机:
    - Closed: 正常接收请求
    - Open: 拒绝所有请求，等待冷却
    - HalfOpen: 允许少量探测请求

    并发安全：使用 asyncio.Lock 保护状态变更
    """

    def __init__(
        self,
        name: str,
        config: CircuitConfig | None = None,
    ):
        self.name = name
        self._config = config or CircuitConfig()
        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._lock = asyncio.Lock()
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        """当前状态"""
        return self._state

    @property
    def stats(self) -> CircuitStats:
        """统计信息"""
        return self._stats

    @property
    def is_open(self) -> bool:
        """是否熔断（拒绝请求）"""
        return self._state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        """是否正常"""
        return self._state == CircuitState.CLOSED

    @property
    def is_half_open(self) -> bool:
        """是否半开（探测恢复）"""
        return self._state == CircuitState.HALF_OPEN

    async def can_execute(self) -> bool:
        """检查是否可以执行请求

        Returns:
            True: 可以执行
            False: 熔断中，拒绝请求
        """
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # 检查是否到达冷却时间
                elapsed = time.time() - self._stats.last_failure_time
                if elapsed >= self._config.recovery_timeout:
                    # 转入半开状态
                    self._transition_to(CircuitState.HALF_OPEN)
                    self._half_open_calls = 0
                    logger.info(
                        f"CircuitBreaker[{self.name}] entering HALF_OPEN "
                        f"after {elapsed:.1f}s recovery timeout"
                    )
                    return True
                # 仍在熔断中
                self._stats.total_rejections += 1
                return False

            if self._state == CircuitState.HALF_OPEN:
                # 半开状态：限制探测次数
                if self._half_open_calls < self._config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                self._stats.total_rejections += 1
                return False

        return False

    async def record_success(self) -> None:
        """记录成功"""
        async with self._lock:
            self._stats.success_count += 1
            self._stats.total_successes += 1
            self._stats.failure_count = 0  # 重置失败计数

            if self._state == CircuitState.HALF_OPEN:
                # 半开状态成功：检查是否达到恢复阈值
                if self._stats.success_count >= self._config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                    logger.info(
                        f"CircuitBreaker[{self.name}] recovered to CLOSED "
                        f"after {self._stats.success_count} successes"
                    )

    async def record_failure(self) -> None:
        """记录失败"""
        async with self._lock:
            self._stats.failure_count += 1
            self._stats.total_failures += 1
            self._stats.last_failure_time = time.time()
            self._stats.success_count = 0  # 重置成功计数

            if self._state == CircuitState.CLOSED:
                # 正常状态：检查是否达到熔断阈值
                if self._stats.failure_count >= self._config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
                    logger.warning(
                        f"CircuitBreaker[{self.name}] tripped to OPEN "
                        f"after {self._stats.failure_count} consecutive failures"
                    )

            elif self._state == CircuitState.HALF_OPEN:
                # 半开状态失败：立即熔断
                self._transition_to(CircuitState.OPEN)
                logger.warning(
                    f"CircuitBreaker[{self.name}] failed probe, back to OPEN"
                )

    def _transition_to(self, new_state: CircuitState) -> None:
        """状态转换"""
        self._state = new_state
        self._stats.last_state_change = time.time()

    async def reset(self) -> None:
        """强制重置"""
        async with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._stats.failure_count = 0
            self._stats.success_count = 0
            self._half_open_calls = 0
            logger.info(f"CircuitBreaker[{self.name}] manually reset to CLOSED")

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


class CircuitBreakerRegistry:
    """熔断器注册表

    管理多个 Provider 的独立熔断器配置。
    借鉴 worldmonitor 的"每个数据域独立熔断配置"设计。
    """

    def __init__(self, default_config: CircuitConfig | None = None):
        self._default_config = default_config or CircuitConfig()
        self._breakers: dict[str, CircuitBreaker] = {}
        self._custom_configs: dict[str, CircuitConfig] = {}
        self._lock = asyncio.Lock()

    async def get_breaker(self, name: str) -> CircuitBreaker:
        """获取或创建熔断器"""
        async with self._lock:
            if name not in self._breakers:
                config = self._custom_configs.get(name, self._default_config)
                self._breakers[name] = CircuitBreaker(name, config)
            return self._breakers[name]

    def configure(self, name: str, config: CircuitConfig) -> None:
        """为特定 Provider 配置熔断器"""
        self._custom_configs[name] = config
        # 如果已有熔断器，更新其配置
        if name in self._breakers:
            self._breakers[name]._config = config

    async def can_execute(self, provider: str) -> bool:
        """检查 Provider 是否可执行"""
        breaker = await self.get_breaker(provider)
        return await breaker.can_execute()

    async def record_success(self, provider: str) -> None:
        """记录 Provider 成功"""
        breaker = await self.get_breaker(provider)
        await breaker.record_success()

    async def record_failure(self, provider: str) -> None:
        """记录 Provider 失败"""
        breaker = await self.get_breaker(provider)
        await breaker.record_failure()

    async def reset(self, provider: str) -> None:
        """重置 Provider 熔断器"""
        breaker = await self.get_breaker(provider)
        await breaker.reset()

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """获取所有熔断器状态"""
        return {name: breaker.get_status() for name, breaker in self._breakers.items()}

    def get_open_providers(self) -> list[str]:
        """获取所有熔断的 Provider"""
        return [
            name for name, breaker in self._breakers.items()
            if breaker.is_open
        ]


# 全局默认实例
_global_registry: CircuitBreakerRegistry | None = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """获取全局熔断器注册表"""
    if _global_registry is None:
        _global_registry = CircuitBreakerRegistry()
    return _global_registry


async def with_circuit_breaker(
    provider: str,
    operation: str,
    registry: CircuitBreakerRegistry | None = None,
) -> bool:
    """在熔断器保护下执行操作的装饰器辅助函数

    Args:
        provider: Provider 名称
        operation: 操作描述（日志）
        registry: 熔断器注册表（默认使用全局）

    Returns:
        True: 可以执行
        False: 熔断中，拒绝执行
    """
    reg = registry or get_circuit_breaker_registry()
    can_run = await reg.can_execute(provider)
    if not can_run:
        logger.warning(
            f"CircuitBreaker blocked {operation} for provider {provider}"
        )
    return can_run