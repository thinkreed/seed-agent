"""
请求队列 - 调度器模块

处理队列调度循环的核心逻辑。
"""

import asyncio
import logging

from src.request_queue_core._types import (
    RequestPriority,
    TurnTicket,
)

logger = logging.getLogger("seed_agent")


class QueueDispatcher:
    """队列调度器"""

    def __init__(
        self,
        critical_queue: asyncio.Queue,
        normal_queues: dict[RequestPriority, asyncio.Queue],
        active_tickets: dict,
        stats,
        config,
        new_request_event: asyncio.Event,
    ):
        self._critical_queue = critical_queue
        self._normal_queues = normal_queues
        self._active_tickets = active_tickets
        self._stats = stats
        self._config = config
        self._new_request_event = new_request_event
        self._running = False
        self._lock = asyncio.Lock()

    async def dispatch_loop(self) -> None:
        """调度循环核心：CRITICAL 优先"""
        while self._running:
            try:
                await self._new_request_event.wait()

                # 1. 先处理 CRITICAL
                ticket = await self._pop_ticket(RequestPriority.CRITICAL)
                if ticket:
                    await self._signal_turn(ticket)
                    await asyncio.sleep(1.0 / self._config.critical_dispatch_rate)
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
                        await asyncio.sleep(1.0 / self._config.normal_dispatch_rate)
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

    def start(self) -> None:
        """启动调度器"""
        self._running = True

    def stop(self) -> None:
        """停止调度器"""
        self._running = False