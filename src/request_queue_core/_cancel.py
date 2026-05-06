"""
请求队列 - 取消模块

处理 ticket 取消逻辑。
"""

import contextlib
import logging

from src.request_queue_core._types import RequestPriority, TurnTicket

logger = logging.getLogger("seed_agent")


class TicketCanceler:
    """Ticket 取消处理器"""

    def __init__(
        self,
        critical_queue,
        normal_queues: dict[RequestPriority,],
        active_tickets: dict[str, TurnTicket],
        stats,
    ):
        self._critical_queue = critical_queue
        self._normal_queues = normal_queues
        self._active_tickets = active_tickets
        self._stats = stats

    async def cancel_ticket(self, ticket_id: str, reason: str = "User cancelled") -> bool:
        """取消指定的 ticket"""
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

    async def cancel_all_tickets(self, reason: str = "Emergency cleanup") -> None:
        """取消所有 ticket"""
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