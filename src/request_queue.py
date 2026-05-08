"""
LLM 请求队列系统 - TurnTicket 模式

模块拆分：_types.py, _stats.py, _dispatcher.py, _cancel.py, _metrics.py, _manager.py
"""

import asyncio
import logging
from collections import deque
from typing import Any

from src.request_queue_core import (
    QueueConfig, QueueDispatcher, QueueFullError, QueueMetrics, QueueStats,
    RequestPriority, TicketCanceler, TurnTicket, TurnWaitTimeoutError,
)
from src.request_queue_core._manager import QueueManager

logger = logging.getLogger("seed_agent")


class RequestQueue:
    """请求队列系统 - TurnTicket 模式"""

    def __init__(self, config: QueueConfig | None = None):
        self.config = config or QueueConfig()
        self._running = False  # 向后兼容

        # 队列结构
        self._critical_queue: deque[TurnTicket] = deque()
        self._normal_queues: dict[RequestPriority, deque[TurnTicket]] = {
            RequestPriority.HIGH: deque(), RequestPriority.NORMAL: deque(), RequestPriority.LOW: deque(),
        }
        self._active_tickets: dict[str, TurnTicket] = {}

        # 控制组件
        self._new_request_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._stats = QueueStats()

        # 拆分模块
        self._dispatcher = QueueDispatcher(
            self._critical_queue, self._normal_queues, self._active_tickets,
            self._stats, self.config, self._new_request_event,
        )
        self._canceler = TicketCanceler(
            self._critical_queue, self._normal_queues, self._active_tickets, self._stats,
        )
        self._metrics = QueueMetrics(
            self._critical_queue, self._normal_queues, self.config, self._stats, False,
        )
        self._manager = QueueManager(self.config, self._stats, self._dispatcher, self._new_request_event)

    # === 指标接口（委托给 Metrics） ===

    get_critical_fill_ratio = lambda self: self._metrics.get_critical_fill_ratio()
    get_normal_fill_ratio = lambda self: self._metrics.get_normal_fill_ratio()
    get_total_fill_ratio = lambda self: self._metrics.get_total_fill_ratio()
    get_queue_size = lambda self: self._metrics.get_queue_size()
    get_stats = lambda self: self._metrics.get_stats()

    # === 核心入口 ===

    async def request_turn(self, priority: RequestPriority = RequestPriority.NORMAL) -> TurnTicket:
        """申请轮次"""
        ticket = TurnTicket(priority=priority)
        async with self._lock:
            if priority == RequestPriority.CRITICAL:
                fill_ratio, threshold = self.get_critical_fill_ratio(), self.config.critical_backpressure_threshold
                if fill_ratio >= threshold:
                    self._stats.record_rejected(priority)
                    raise QueueFullError(fill_ratio, threshold, "critical")
                self._critical_queue.append(ticket)
            else:
                fill_ratio, threshold = self.get_normal_fill_ratio(), self.config.normal_backpressure_threshold
                if fill_ratio >= threshold:
                    self._stats.record_rejected(priority)
                    raise QueueFullError(fill_ratio, threshold, "normal")
                self._normal_queues[priority].append(ticket)
            self._active_tickets[ticket.id] = ticket
        self._stats.record_submit(priority)
        self._new_request_event.set()
        logger.debug(f"Ticket {ticket.id} submitted (priority={priority.name})")
        return ticket

    # === 向后兼容接口 ===

    async def _pop_ticket(self, priority: RequestPriority) -> TurnTicket | None:
        """向后兼容：从队列弹出 ticket"""
        async with self._lock:
            if priority == RequestPriority.CRITICAL and self._critical_queue:
                return self._critical_queue.popleft()
            elif self._normal_queues.get(priority):
                return self._normal_queues[priority].popleft()
        return None

    # === 调度器生命周期 ===

    async def start_dispatcher(self) -> None:
        """启动调度器"""
        await self._manager.start()
        self._running = True

    async def stop_dispatcher(self) -> None:
        """停止调度器"""
        await self._manager.stop()
        self._running = False

    # === 取消接口（委托给 Canceler） ===

    async def cancel_ticket(self, ticket_id: str, reason: str = "User cancelled") -> bool:
        """取消指定 ticket"""
        async with self._lock:
            return await self._canceler.cancel_ticket(ticket_id, reason)

    async def cancel_all_tickets(self, reason: str = "Emergency cleanup") -> None:
        """取消所有 ticket"""
        async with self._lock:
            await self._canceler.cancel_all_tickets(reason)

    async def cancel_all_by_priority(self, priority: RequestPriority, reason: str = "Batch cancel") -> None:
        """取消指定优先级的 ticket"""
        async with self._lock:
            await self._canceler.cancel_all_by_priority(priority, reason)


__all__ = ["QueueConfig", "QueueFullError", "QueueStats", "RequestPriority", "RequestQueue", "TurnTicket", "TurnWaitTimeoutError"]