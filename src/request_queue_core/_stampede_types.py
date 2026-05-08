"""
Stampede Protection 类型定义

包含配置类、条目类和统计类。
"""

import asyncio
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class StampedeConfig:
    """Stampede Protection 配置"""
    wait_timeout: float = 30.0       # 等待刷新的最大时间
    result_ttl: float = 60.0         # 结果缓存时间
    max_waiters: int = 100           # 最大等待者数量


@dataclass
class StampedeEntry(Generic[T]):
    """Stampede 条目"""
    key: str
    refresh_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    is_refreshing: bool = False
    result: T | None = None
    result_time: float = 0.0
    error: Exception | None = None
    waiter_count: int = 0
    refresh_task: asyncio.Task[T] | None = None


@dataclass
class StampedeStats:
    """Stampede 统计"""
    total_requests: int = 0
    refresh_requests: int = 0      # 实际执行刷新的请求
    shared_requests: int = 0       # 共享结果的请求
    timeout_requests: int = 0      # 等待超时的请求
    error_requests: int = 0        # 刷新失败的请求
    cache_hits: int = 0            # 直接缓存命中