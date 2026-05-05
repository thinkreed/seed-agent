"""
请求队列核心模块

包含请求队列的类型、统计和调整逻辑。
"""

from src.request_queue_core._types import (
    QueueConfig,
    QueueFullError,
    RequestPriority,
    TurnTicket,
    TurnWaitTimeoutError,
    DISPATCH_LOOP_INTERVAL,
)
from src.request_queue_core._stats import QueueStats, ConfigAdjuster

__all__ = [
    "RequestPriority",
    "QueueFullError",
    "TurnWaitTimeoutError",
    "TurnTicket",
    "QueueConfig",
    "QueueStats",
    "ConfigAdjuster",
    "DISPATCH_LOOP_INTERVAL",
]