"""
请求队列核心模块

包含请求队列的类型、统计、调度、取消和指标逻辑。

模块拆分：
- _types.py: 类型定义（QueueConfig, TurnTicket, RequestPriority 等）
- _stats.py: 统计和配置调整
- _dispatcher.py: 调度循环
- _cancel.py: 取消逻辑
- _metrics.py: 指标计算
- _manager.py: 调度器生命周期管理
"""

from src.request_queue_core._cancel import TicketCanceler
from src.request_queue_core._dispatcher import QueueDispatcher
from src.request_queue_core._manager import QueueManager
from src.request_queue_core._metrics import QueueMetrics
from src.request_queue_core._stats import ConfigAdjuster, QueueStats
from src.request_queue_core._types import (
    DISPATCH_LOOP_INTERVAL,
    QueueConfig,
    QueueFullError,
    RequestPriority,
    TurnTicket,
    TurnWaitTimeoutError,
)

__all__ = [
    "DISPATCH_LOOP_INTERVAL",
    "ConfigAdjuster",
    "QueueConfig",
    "QueueDispatcher",
    "QueueFullError",
    "QueueManager",
    "QueueMetrics",
    "QueueStats",
    "RequestPriority",
    "TicketCanceler",
    "TurnTicket",
    "TurnWaitTimeoutError",
]