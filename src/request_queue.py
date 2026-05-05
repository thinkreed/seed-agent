"""
LLM 请求队列系统 - TurnTicket 模式

实现异步请求调度、优先级队列和反压机制
核心设计：队列只管"轮次分配"，不介入执行细节

重构说明：
- 类型定义移至 request_queue_core/_types.py
- 统计逻辑移至 request_queue_core/_stats.py
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

    def get_critical_fill_ratio(self) -> float:
        """获取 CRITICAL 队列填充率"""
        return len(self._critical_queue) / self.config.critical_max_size

    def get_normal_fill_ratio(self) -> float:
        """获取普通队列填充率"""
        total = sum(len(q) for q in self._normal_queues.values())
        return total / self.config.normal_max_size

    def get_total_fill_ratio(self) -> float:
        """获取总体队列填充率"""
        critical_fill = self.get_critical_fill_ratio()
        normal_fill = self.get_normal_fill_ratio()
        return critical_fill * 0.2 + normal_fill * 0.8

    def get_queue_size(self) -> dict[str, int]:
        """获取各队列大小"""
        return {
            "critical": len(self._critical_queue),
            "high": len(self._normal_queues[RequestPriority.HIGH]),
            "normal": len(self._normal_queues[RequestPriority.NORMAL]),
            "low": len(self._normal_queues[RequestPriority.LOW]),
            "total": len(self._critical_queue)
            + sum(len(q) for q in self._normal_queues.values()),
        }

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

    async def start_dispatcher(self) -> None:
        """启动异步调度器"""
        if self._running:
            logger.warning("Dispatcher already running")
            return

        self._running = True
        self._dispatcher_task = asyncio.create_task(self._dispatch_loop())

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

    async def _dispatch_loop(self) -> None:
        """调度循环核心：CRITICAL 优先"""
        while self._running:
            try:
                await self._new_request_event.wait()

                # 1. 先处理 CRITICAL
                ticket = await self._pop_ticket(RequestPriority.CRITICAL)
                if ticket:
                    await self._signal_turn(ticket)
                    await asyncio.sleep(1.0 / self.config.critical_dispatch_rate)
                    continue

                # 2. CRITICAL 空，处理普通队列
                for priority in [
                    RequestPriority.HIGH,
                    RequestPriority.NORMAL,
                    RequestPriority.LOW,
                ]:
                    ticket = await self._pop_ticket(priority)
                    if ticket:
                        await self._signal_turn(ticket)
                        await asyncio.sleep(1.0 / self.config.normal_dispatch_rate)
                        break

                # 3. 所有队列都空
                if not await self._has_pending_tickets():
                    self._new_request_event.clear()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Dispatch loop error: {e}")
                await asyncio.sleep(1.0)

    async def _pop_ticket(self, priority: RequestPriority) -> TurnTicket | None:
        """从指定优先级队列弹出 ticket"""
        async with self._lock:
            if priority == RequestPriority.CRITICAL:
                if self._critical_queue:
                    return self._critical_queue.popleft()
            elif self._normal_queues[priority]:
                return self._normal_queues[priority].popleft()
        return None

    async def _signal_turn(self, ticket: TurnTicket):
        """通知 ticket 轮次到了"""
        ticket.signal_turn()
        self._stats.record_signal(ticket.priority)

        wait_duration = ticket.get_wait_duration()
        self._stats.record_wait_time(ticket.priority, wait_duration)

        async with self._lock:
            self._active_tickets.pop(ticket.id, None)

        logger.debug(
            f"Ticket {ticket.id} signaled (priority={ticket.priority.name}, "
            f"wait_duration={wait_duration:.2f}s)"
        )

    async def _has_pending_tickets(self) -> bool:
        """检查是否有待处理的 ticket"""
        async with self._lock:
            if self._critical_queue:
                return True
            for q in self._normal_queues.values():
                if q:
                    return True
        return False

    async def cancel_ticket(self, ticket_id: str, reason: str = "User cancelled") -> bool:
        """取消指定的 ticket"""
        async with self._lock:
            ticket = self._active_tickets.get(ticket_id)
            if not ticket:
                return False

            if ticket.priority == RequestPriority.CRITICAL:
                with contextlib.suppress(ValueError):
                    self._critical_queue.remove(ticket)
            else:
                with contextlib.suppress(ValueError):
                    self._normal_queues[ticket.priority].remove(ticket)

            ticket.cancel(reason)
            self._active_tickets.pop(ticket_id, None)
            self._stats.record_cancelled(ticket.priority)

            logger.info(f"Ticket {ticket_id} cancelled: reason={reason}")
            return True

    async def cancel_all_tickets(self, reason: str = "Emergency cleanup"):
        """取消所有 ticket"""
        async with self._lock:
            for ticket in list(self._critical_queue):
                ticket.cancel(reason)
                self._stats.record_cancelled(RequestPriority.CRITICAL)
            self._critical_queue.clear()

            for priority, queue in self._normal_queues.items():
                for ticket in list(queue):
                    ticket.cancel(reason)
                    self._stats.record_cancelled(priority)
                queue.clear()

            self._active_tickets.clear()
            logger.info(f"All tickets cancelled: reason={reason}")

    async def cancel_all_by_priority(
        self, priority: RequestPriority, reason: str = "Batch cancel"
    ) -> None:
        """取消指定优先级的所有 ticket"""
        async with self._lock:
            if priority == RequestPriority.CRITICAL:
                for ticket in list(self._critical_queue):
                    ticket.cancel(reason)
                    self._stats.record_cancelled(RequestPriority.CRITICAL)
                self._critical_queue.clear()
            else:
                for ticket in list(self._normal_queues[priority]):
                    ticket.cancel(reason)
                    self._stats.record_cancelled(priority)
                self._normal_queues[priority].clear()

            # 从活跃索引中移除
            for ticket_id in list(self._active_tickets.keys()):
                ticket = self._active_tickets[ticket_id]
                if ticket.priority == priority:
                    self._active_tickets.pop(ticket_id, None)

            logger.info(f"Cancelled {priority.name} tickets: reason={reason}")

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

    def get_stats(self) -> dict[str, Any]:
        """获取队列统计信息"""
        return {
            "queue_lengths": self.get_queue_size(),
            "fill_ratios": {
                "critical": self.get_critical_fill_ratio(),
                "normal": self.get_normal_fill_ratio(),
                "total": self.get_total_fill_ratio(),
            },
            "config": {
                "critical_max_size": self.config.critical_max_size,
                "critical_backpressure_threshold": self.config.critical_backpressure_threshold,
                "critical_dispatch_rate": self.config.critical_dispatch_rate,
                "normal_max_size": self.config.normal_max_size,
                "normal_backpressure_threshold": self.config.normal_backpressure_threshold,
                "normal_dispatch_rate": self.config.normal_dispatch_rate,
                "auto_adjust_enabled": self.config.auto_adjust_enabled,
            },
            "stats": self._stats.get_stats_dict(),
            "running": self._running,
        }


__all__ = [
    "RequestQueue",
    "RequestPriority",
    "QueueConfig",
    "TurnTicket",
    "QueueFullError",
    "TurnWaitTimeoutError",
    "QueueStats",
]