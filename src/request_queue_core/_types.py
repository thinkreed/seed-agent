"""
请求队列类型定义

包含所有数据类型、枚举和配置类定义。
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum


class RequestPriority(IntEnum):
    """请求优先级"""

    CRITICAL = 0  # 用户直接交互，最高优先级
    HIGH = 1  # RalphLoop 迭代
    NORMAL = 2  # Subagent 任务
    LOW = 3  # Scheduler 后台


class QueueFullError(Exception):
    """队列已满异常"""

    def __init__(self, fill_ratio: float, threshold: float, queue_type: str):
        self.fill_ratio = fill_ratio
        self.threshold = threshold
        self.queue_type = queue_type
        super().__init__(
            f"Queue ({queue_type}) at {fill_ratio:.1%} capacity "
            f"(threshold: {threshold:.1%}), rejecting requests"
        )


class TurnWaitTimeoutError(Exception):
    """轮次等待超时"""

    def __init__(self, ticket_id: str, waited_seconds: float, queue_status: dict):
        self.ticket_id = ticket_id
        self.waited_seconds = waited_seconds
        self.queue_status = queue_status
        super().__init__(
            f"Ticket {ticket_id} waited {waited_seconds}s for turn, "
            f"queue status: {queue_status}"
        )


@dataclass
class TurnTicket:
    """轮次票 - 代表"轮到你执行了"的信号"""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    priority: RequestPriority = RequestPriority.NORMAL
    created_at: float = field(default_factory=time.time)

    _turn_event: asyncio.Event = field(default_factory=asyncio.Event)
    _turn_time: float | None = None
    _cancelled: bool = False
    _cancel_reason: str | None = None

    async def wait_for_turn(self, timeout: float) -> None:
        """等待轮次到达"""
        try:
            await asyncio.wait_for(self._turn_event.wait(), timeout)
        except TimeoutError:
            raise TurnWaitTimeoutError(self.id, timeout, {}) from None

        if self._cancelled:
            raise asyncio.CancelledError(self._cancel_reason)

    def signal_turn(self) -> None:
        """调度器通知：轮次到了"""
        self._turn_time = time.time()
        self._turn_event.set()

    def cancel(self, reason: str = "User cancelled") -> None:
        """取消排队"""
        self._cancelled = True
        self._cancel_reason = reason
        self._turn_event.set()

    def get_wait_duration(self) -> float:
        """获取等待时长"""
        if self._turn_time:
            return self._turn_time - self.created_at
        return time.time() - self.created_at

    def is_signaled(self) -> bool:
        """是否已分配轮次"""
        return self._turn_event.is_set() and not self._cancelled


@dataclass
class QueueConfig:
    """队列配置"""

    # CRITICAL 队列配置
    critical_max_size: int = 10
    critical_backpressure_threshold: float = 0.9
    critical_dispatch_rate: float = 10.0
    critical_target_wait_time: float = 5.0

    # 普通队列配置
    normal_max_size: int = 50
    normal_backpressure_threshold: float = 0.8
    normal_dispatch_rate: float = 0.33
    normal_target_wait_time: float = 30.0

    # 自动调整
    auto_adjust_enabled: bool = True
    adjust_interval: float = 60.0


# 自动调整常量
MAX_CRITICAL_DISPATCH_RATE = 50.0
MAX_CRITICAL_QUEUE_SIZE = 30
CRITICAL_SIZE_INCREMENT = 5
REJECT_RATE_THRESHOLD = 0.1
BACKPRESSURE_INCREMENT = 0.05
MAX_BACKPRESSURE_THRESHOLD = 0.95
MAX_NORMAL_DISPATCH_RATE = 5.0
DISPATCH_RATE_MULTIPLIER = 1.2
STATS_WINDOW_SIZE = 100
DISPATCH_LOOP_INTERVAL = 30.0