"""
LLM 请求队列系统 - TurnTicket 模式

实现异步请求调度、优先级队列和反压机制
核心设计：队列只管"轮次分配"，不介入执行细节

重构说明：
- 类型定义移至 request_queue_core/_types.py
- 统计逻辑移至 request_queue_core/_stats.py
- 调度逻辑移至 request_queue_core/_dispatcher.py
- 取消逻辑移至 request_queue_core/_cancel.py
- 指标计算移至 request_queue_core/_metrics.py
"""

import asyncio
import contextlib
import logging
from collections import deque
from typing import Any

from src.request_queue_core import (
    ConfigAdjuster,
    DISPATCH_LOOP_INTERVAL,
    QueueConfig,
    QueueFullError,
    QueueStats,
    QueueDispatcher,
    TicketCanceler,
    QueueMetrics,
    RequestPriority,
    TurnTicket,
    TurnWaitTimeoutError,
)

logger = logging.getLogger("seed_agent")


class RequestQueue:
    """请求队列系统 - TurnTicket 模式"""

    def __init__(self, config: QueueConfig | None = None):
        self.config = config or QueueConfig()

        # CRITICAL 独立队列
        self._critical_queue: deque[TurnTicket] = deque()

        # 普通队列（HIGH/NORMAL/LOW 共享）
        self._normal_queues: dict[RequestPriority, deque[TurnTicket]] = {
            RequestPriority.HIGH: deque(),
            RequestPriority.NORMAL: deque(),
            RequestPriority.LOW: deque(),
        }

        # 所有活跃 ticket 的索引
        self._active_tickets: dict[str, TurnTicket] = {}

        # 调度控制
        self._dispatcher_task: asyncio.Task | None = None
        self._new_request_event = asyncio.Event()
        self._running = False
        self._lock = asyncio.Lock()

        # 统计和调整
        self._stats = QueueStats()
        self._adjuster = ConfigAdjuster()
        self._adjust_task: asyncio.Task | None = None

        # 拆分模块组件
        self._dispatcher = QueueDispatcher(
            self._critical_queue,
            self._normal_queues,
            self._active_tickets,
            self._stats,
            self.config,
            self._new_request_event,
        )
        self._canceler = TicketCanceler(
            self._critical_queue,
            self._normal_queues,
            self._active_tickets,
            self._stats,
        )
        self._metrics = QueueMetrics(
            self._critical_queue,
            self._normal_queues,
            self.config,
            self._stats,
            self._running,
        )

    # === 指标接口 ===

    def get_critical_fill_ratio(self) -> float:
        """获取 CRITICAL 队列填充率"""
        return self._metrics.get_critical_fill_ratio()

    def get_normal_fill_ratio(self) -> float:
        """获取普通队列填充率"""
        return self._metrics.get_normal_fill_ratio()

    def get_total_fill_ratio(self) -> float:
        """获取总体队列填充率"""
        return self._metrics.get_total_fill_ratio()

    def get_queue_size(self) -> dict[str, int]:
        """获取各队列大小"""
        return self._metrics.get_queue_size()

    def get_stats(self) -> dict[str, Any]:
        """获取队列统计信息"""
        return self._metrics.get_stats()

    # === 核心入口 ===

    async def request_turn(
        self, priority: RequestPriority = RequestPriority.NORMAL
    ) -> TurnTicket:
        """申请轮次（核心入口）"""
        ticket = TurnTicket(priority=priority)

        async with self._lock:
            if priority == RequestPriority.CRITICAL:
                fill_ratio = self.get_critical_fill_ratio()
                threshold = self.config.critical_backpressure_threshold

                if fill_ratio >= threshold:
                    self._stats.record_rejected(priority)
                    raise QueueFullError(fill_ratio, threshold, "critical")

                self._critical_queue.append(ticket)
            else:
                fill_ratio = self.get_normal_fill_ratio()
                threshold = self.config.normal_backpressure_threshold

                if fill_ratio >= threshold:
                    self._stats.record_rejected(priority)
                    raise QueueFullError(fill_ratio, threshold, "normal")

                self._normal_queues[priority].append(ticket)

            self._active_tickets[ticket.id] = ticket

        self._stats.record_submit(priority)
        self._new_request_event.set()

        logger.debug(f"Ticket {ticket.id} submitted (priority={priority.name})")
        return ticket

    # === 调度器 ===

    async def _pop_ticket(self, priority: RequestPriority) -> TurnTicket | None:
        """向后兼容：从队列弹出 ticket"""
        async with self._lock:
            if priority == RequestPriority.CRITICAL:
                if self._critical_queue:
                    return self._critical_queue.popleft()
            elif self._normal_queues[priority]:
                return self._normal_queues[priority].popleft()
        return None

    async def _signal_turn(self, ticket: TurnTicket) -> None:
        """向后兼容：通知轮次"""
        ticket.signal_turn()
        self._stats.record_signal(ticket.priority)
        async with self._lock:
            self._active_tickets.pop(ticket.id, None)

    async def _has_pending_tickets(self) -> bool:
        """向后兼容：检查是否有待处理 ticket"""
        async with self._lock:
            if self._critical_queue:
                return True
            for q in self._normal_queues.values():
                if q:
                    return True
        return False

    async def start_dispatcher(self) -> None:
        """启动异步调度器"""
        if self._running:
            logger.warning("Dispatcher already running")
            return

        self._running = True
        self._dispatcher.start()
        self._dispatcher_task = asyncio.create_task(self._dispatcher.dispatch_loop())

        if self.config.auto_adjust_enabled:
            self._adjust_task = asyncio.create_task(self._adjust_loop())

        logger.info(
            f"Request queue dispatcher started "
            f"(critical_rate={self.config.critical_dispatch_rate}, "
            f"normal_rate={self.config.normal_dispatch_rate})"
        )

    async def stop_dispatcher(self) -> None:
        """停止调度器"""
        self._running = False
        self._dispatcher.stop()

        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._dispatcher_task
            self._dispatcher_task = None

        if self._adjust_task:
            self._adjust_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._adjust_task
            self._adjust_task = None

        logger.info("Request queue dispatcher stopped")

    async def _adjust_loop(self) -> None:
        """智能调整循环"""
        while self._running:
            try:
                await asyncio.sleep(self.config.adjust_interval)
                self._adjuster.adjust_config(self.config, self._stats)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Adjust loop error: {e}")
                await asyncio.sleep(DISPATCH_LOOP_INTERVAL)

    # === 取消接口 ===

    async def cancel_ticket(self, ticket_id: str, reason: str = "User cancelled") -> bool:
        """取消指定的 ticket"""
        async with self._lock:
            return await self._canceler.cancel_ticket(ticket_id, reason)

    async def cancel_all_tickets(self, reason: str = "Emergency cleanup") -> None:
        """取消所有 ticket"""
        async with self._lock:
            await self._canceler.cancel_all_tickets(reason)

    async def cancel_all_by_priority(
        self, priority: RequestPriority, reason: str = "Batch cancel"
    ) -> None:
        """取消指定优先级的所有 ticket"""
        async with self._lock:
            await self._canceler.cancel_all_by_priority(priority, reason)


__all__ = [
    "RequestQueue",
    "RequestPriority",
    "QueueConfig",
    "TurnTicket",
    "QueueFullError",
    "TurnWaitTimeoutError",
    "QueueStats",
]