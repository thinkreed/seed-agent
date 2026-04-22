"""LLM 请求队列系统 - TurnTicket 模式

实现异步请求调度、优先级队列和反压机制
核心设计：队列只管"轮次分配"，不介入执行细节
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Deque, Optional, Any, List
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum

logger = logging.getLogger("seed_agent")


class RequestPriority(IntEnum):
    """请求优先级"""
    CRITICAL = 0    # 用户直接交互，最高优先级，独立队列
    HIGH = 1        # RalphLoop 迭代，优先处理
    NORMAL = 2      # Subagent 任务，标准处理
    LOW = 3         # Scheduler 后台，队列处理


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


class TurnWaitTimeout(Exception):
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
    """轮次票 - 代表"轮到你执行了"的信号

    核心理念：队列只管"轮次分配"，不介入执行细节
    """

    # 基本信息
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    priority: RequestPriority = RequestPriority.NORMAL
    created_at: float = field(default_factory=time.time)

    # 轮次信号
    _turn_event: asyncio.Event = field(default_factory=asyncio.Event)
    _turn_time: Optional[float] = None
    _cancelled: bool = False
    _cancel_reason: Optional[str] = None

    async def wait_for_turn(self, timeout: float) -> None:
        """等待轮次到达

        Args:
            timeout: 最大等待时间（秒）

        Raises:
            TurnWaitTimeout: 等待超时
            asyncio.CancelledError: 被取消
        """
        try:
            await asyncio.wait_for(self._turn_event.wait(), timeout)
        except asyncio.TimeoutError:
            raise TurnWaitTimeout(self.id, timeout, {})

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
        self._turn_event.set()  # 唤醒等待者，让其抛出 CancelledError

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
    """队列配置（可动态调整）"""

    # CRITICAL 队列配置
    critical_max_size: int = 10
    critical_backpressure_threshold: float = 0.9
    critical_dispatch_rate: float = 10.0
    critical_target_wait_time: float = 5.0

    # 普通队列配置（HIGH/NORMAL/LOW 共享）
    normal_max_size: int = 50
    normal_backpressure_threshold: float = 0.8
    normal_dispatch_rate: float = 0.33
    normal_target_wait_time: float = 30.0

    # 自动调整
    auto_adjust_enabled: bool = True
    adjust_interval: float = 60.0  # 每60秒检查一次


@dataclass
class QueueStats:
    """队列统计（用于智能调整和监控）"""

    # 等待时间记录（每个优先级最近100条）
    wait_times: Dict[RequestPriority, List[float]] = field(
        default_factory=lambda: {p: [] for p in RequestPriority}
    )

    # 计数
    submitted: Dict[RequestPriority, int] = field(
        default_factory=lambda: {p: 0 for p in RequestPriority}
    )
    signaled: Dict[RequestPriority, int] = field(
        default_factory=lambda: {p: 0 for p in RequestPriority}
    )
    rejected: Dict[RequestPriority, int] = field(
        default_factory=lambda: {p: 0 for p in RequestPriority}
    )
    cancelled: Dict[RequestPriority, int] = field(
        default_factory=lambda: {p: 0 for p in RequestPriority}
    )

    def record_submit(self, priority: RequestPriority):
        self.submitted[priority] += 1

    def record_signal(self, priority: RequestPriority):
        self.signaled[priority] += 1

    def record_rejected(self, priority: RequestPriority):
        self.rejected[priority] += 1

    def record_cancelled(self, priority: RequestPriority):
        self.cancelled[priority] += 1

    def record_wait_time(self, priority: RequestPriority, duration: float):
        self.wait_times[priority].append(duration)
        # 只保留最近100条
        if len(self.wait_times[priority]) > 100:
            self.wait_times[priority] = self.wait_times[priority][-100:]

    def get_avg_wait_time(self, priority: RequestPriority) -> float:
        times = self.wait_times[priority]
        if not times:
            return 0.0
        return sum(times) / len(times)

    def get_p95_wait_time(self, priority: RequestPriority) -> float:
        times = self.wait_times[priority]
        if not times:
            return 0.0
        sorted_times = sorted(times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]

    def get_reject_rate(self, priority: RequestPriority) -> float:
        submitted = self.submitted[priority]
        if submitted == 0:
            return 0.0
        return self.rejected[priority] / submitted

    def get_stats_dict(self) -> Dict[str, Any]:
        """获取统计字典"""
        return {
            "submitted": {p.name: self.submitted[p] for p in RequestPriority},
            "signaled": {p.name: self.signaled[p] for p in RequestPriority},
            "rejected": {p.name: self.rejected[p] for p in RequestPriority},
            "cancelled": {p.name: self.cancelled[p] for p in RequestPriority},
            "avg_wait_times": {p.name: self.get_avg_wait_time(p) for p in RequestPriority},
            "p95_wait_times": {p.name: self.get_p95_wait_time(p) for p in RequestPriority},
            "reject_rates": {p.name: self.get_reject_rate(p) for p in RequestPriority},
        }


class RequestQueue:
    """请求队列系统 - TurnTicket 模式

    特性:
    - CRITICAL 独立队列，最高优先级
    - 多优先级队列（HIGH/NORMAL/LOW 共享）
    - TurnTicket 模式：只管轮次分配，不介入执行
    - 反压机制（队列满时拒绝新请求）
    - 智能配置调整
    """

    def __init__(self, config: QueueConfig = None):
        """
        Args:
            config: 队列配置，默认使用默认配置
        """
        self.config = config or QueueConfig()

        # CRITICAL 独立队列
        self._critical_queue: Deque[TurnTicket] = deque()

        # 普通队列（HIGH/NORMAL/LOW 共享）
        self._normal_queues: Dict[RequestPriority, Deque[TurnTicket]] = {
            RequestPriority.HIGH: deque(),
            RequestPriority.NORMAL: deque(),
            RequestPriority.LOW: deque(),
        }

        # 所有活跃 ticket 的索引（用于取消）
        self._active_tickets: Dict[str, TurnTicket] = {}

        # 调度控制
        self._dispatcher_task: Optional[asyncio.Task] = None
        self._new_request_event = asyncio.Event()
        self._running = False
        self._lock = asyncio.Lock()

        # 统计
        self._stats = QueueStats()

        # 智能调整
        self._adjust_task: Optional[asyncio.Task] = None

    def get_critical_fill_ratio(self) -> float:
        """获取 CRITICAL 队列填充率"""
        return len(self._critical_queue) / self.config.critical_max_size

    def get_normal_fill_ratio(self) -> float:
        """获取普通队列填充率"""
        total = sum(len(q) for q in self._normal_queues.values())
        return total / self.config.normal_max_size

    def get_total_fill_ratio(self) -> float:
        """获取总体队列填充率（用于负载因子计算）"""
        critical_fill = self.get_critical_fill_ratio()
        normal_fill = self.get_normal_fill_ratio()
        # 综合填充率，CRITICAL 权重较低
        return critical_fill * 0.2 + normal_fill * 0.8

    def get_queue_size(self) -> Dict[str, int]:
        """获取各队列大小"""
        return {
            "critical": len(self._critical_queue),
            "high": len(self._normal_queues[RequestPriority.HIGH]),
            "normal": len(self._normal_queues[RequestPriority.NORMAL]),
            "low": len(self._normal_queues[RequestPriority.LOW]),
            "total": len(self._critical_queue) + sum(len(q) for q in self._normal_queues.values()),
        }

    async def request_turn(
        self,
        priority: RequestPriority = RequestPriority.NORMAL
    ) -> TurnTicket:
        """申请轮次（核心入口）

        Args:
            priority: 请求优先级

        Returns:
            TurnTicket: 轮次票

        Raises:
            QueueFullError: 队列已满
        """
        ticket = TurnTicket(priority=priority)

        async with self._lock:
            # CRITICAL 使用独立队列
            if priority == RequestPriority.CRITICAL:
                fill_ratio = self.get_critical_fill_ratio()
                threshold = self.config.critical_backpressure_threshold
                max_size = self.config.critical_max_size

                if fill_ratio >= threshold:
                    self._stats.record_rejected(priority)
                    raise QueueFullError(fill_ratio, threshold, "critical")

                self._critical_queue.append(ticket)
            else:
                # HIGH/NORMAL/LOW 共享普通队列
                fill_ratio = self.get_normal_fill_ratio()
                threshold = self.config.normal_backpressure_threshold
                max_size = self.config.normal_max_size

                if fill_ratio >= threshold:
                    self._stats.record_rejected(priority)
                    raise QueueFullError(fill_ratio, threshold, "normal")

                self._normal_queues[priority].append(ticket)

            # 记录活跃 ticket
            self._active_tickets[ticket.id] = ticket
            self._stats.record_submit(priority)

        # 触发调度器
        self._new_request_event.set()

        logger.debug(f"Ticket {ticket.id} submitted (priority={priority.name})")
        return ticket

    async def start_dispatcher(self):
        """启动异步调度器"""
        if self._running:
            logger.warning("Dispatcher already running")
            return

        self._running = True
        self._dispatcher_task = asyncio.create_task(self._dispatch_loop())

        # 启动智能调整任务（如果启用）
        if self.config.auto_adjust_enabled:
            self._adjust_task = asyncio.create_task(self._adjust_loop())

        logger.info(
            f"Request queue dispatcher started "
            f"(critical_rate={self.config.critical_dispatch_rate}, "
            f"normal_rate={self.config.normal_dispatch_rate})"
        )

    async def stop_dispatcher(self):
        """停止调度器"""
        self._running = False

        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
            self._dispatcher_task = None

        if self._adjust_task:
            self._adjust_task.cancel()
            try:
                await self._adjust_task
            except asyncio.CancelledError:
                pass
            self._adjust_task = None

        logger.info("Request queue dispatcher stopped")

    async def _dispatch_loop(self):
        """调度循环核心：CRITICAL 优先"""
        while self._running:
            try:
                # 等待新请求
                await self._new_request_event.wait()

                # 1. 先处理 CRITICAL（最高优先级）
                ticket = await self._pop_ticket(RequestPriority.CRITICAL)
                if ticket:
                    await self._signal_turn(ticket)
                    await asyncio.sleep(1.0 / self.config.critical_dispatch_rate)
                    continue

                # 2. CRITICAL 空，处理普通队列（按优先级）
                for priority in [RequestPriority.HIGH, RequestPriority.NORMAL, RequestPriority.LOW]:
                    ticket = await self._pop_ticket(priority)
                    if ticket:
                        await self._signal_turn(ticket)
                        await asyncio.sleep(1.0 / self.config.normal_dispatch_rate)
                        break

                # 3. 所有队列都空，清除事件
                if not await self._has_pending_tickets():
                    self._new_request_event.clear()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Dispatch loop error: {e}")
                await asyncio.sleep(1.0)

    async def _pop_ticket(self, priority: RequestPriority) -> Optional[TurnTicket]:
        """从指定优先级队列弹出 ticket"""
        async with self._lock:
            if priority == RequestPriority.CRITICAL:
                if self._critical_queue:
                    return self._critical_queue.popleft()
            else:
                if self._normal_queues[priority]:
                    return self._normal_queues[priority].popleft()
        return None

    async def _signal_turn(self, ticket: TurnTicket):
        """通知 ticket 轮次到了"""
        ticket.signal_turn()
        self._stats.record_signal(ticket.priority)

        # 记录等待时间
        wait_duration = ticket.get_wait_duration()
        self._stats.record_wait_time(ticket.priority, wait_duration)

        # 从活跃索引中移除
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
        """取消指定的 ticket

        Args:
            ticket_id: ticket ID
            reason: 取消原因

        Returns:
            是否成功取消
        """
        async with self._lock:
            ticket = self._active_tickets.get(ticket_id)
            if not ticket:
                return False

            # 从队列中移除
            if ticket.priority == RequestPriority.CRITICAL:
                try:
                    self._critical_queue.remove(ticket)
                except ValueError:
                    pass
            else:
                try:
                    self._normal_queues[ticket.priority].remove(ticket)
                except ValueError:
                    pass

            # 取消 ticket
            ticket.cancel(reason)
            self._active_tickets.pop(ticket_id, None)
            self._stats.record_cancelled(ticket.priority)

            logger.info(f"Ticket {ticket_id} cancelled: reason={reason}")
            return True

    async def cancel_all_by_priority(self, priority: RequestPriority, reason: str = "Batch cancel"):
        """取消指定优先级的所有 ticket"""
        async with self._lock:
            if priority == RequestPriority.CRITICAL:
                tickets = list(self._critical_queue)
                self._critical_queue.clear()
            else:
                tickets = list(self._normal_queues[priority])
                self._normal_queues[priority].clear()

            for ticket in tickets:
                ticket.cancel(reason)
                self._active_tickets.pop(ticket.id, None)
                self._stats.record_cancelled(priority)

            logger.info(f"Cancelled {len(tickets)} tickets with priority={priority.name}")

    async def cancel_all_tickets(self, reason: str = "Emergency cleanup"):
        """取消所有 ticket"""
        async with self._lock:
            # CRITICAL
            for ticket in list(self._critical_queue):
                ticket.cancel(reason)
                self._stats.record_cancelled(RequestPriority.CRITICAL)
            self._critical_queue.clear()

            # 普通
            for priority, queue in self._normal_queues.items():
                for ticket in list(queue):
                    ticket.cancel(reason)
                    self._stats.record_cancelled(priority)
                queue.clear()

            self._active_tickets.clear()
            logger.info(f"All tickets cancelled: reason={reason}")

    async def _adjust_loop(self):
        """智能调整循环"""
        while self._running:
            try:
                await asyncio.sleep(self.config.adjust_interval)
                await self._adjust_config()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Adjust loop error: {e}")
                await asyncio.sleep(30.0)

    async def _adjust_config(self):
        """根据统计数据智能调整配置"""
        # 1. CRITICAL 队列调整
        critical_avg_wait = self._stats.get_avg_wait_time(RequestPriority.CRITICAL)
        critical_p95_wait = self._stats.get_p95_wait_time(RequestPriority.CRITICAL)

        # 如果 CRITICAL 平均等待超过目标，增加调度速率
        if critical_avg_wait > self.config.critical_target_wait_time:
            old_rate = self.config.critical_dispatch_rate
            self.config.critical_dispatch_rate *= 1.2
            self.config.critical_dispatch_rate = min(self.config.critical_dispatch_rate, 50.0)

            if self.config.critical_dispatch_rate != old_rate:
                logger.info(
                    f"Auto-adjust: CRITICAL dispatch_rate increased to "
                    f"{self.config.critical_dispatch_rate:.2f}"
                )

            # 如果 P95 很高，增加容量
            if critical_p95_wait > self.config.critical_target_wait_time * 2:
                old_size = self.config.critical_max_size
                self.config.critical_max_size = min(
                    self.config.critical_max_size + 5,
                    30  # 最大不超过 30
                )
                if self.config.critical_max_size != old_size:
                    logger.info(
                        f"Auto-adjust: CRITICAL max_size increased to "
                        f"{self.config.critical_max_size}"
                    )

        # 2. 反压阈值调整（根据拒绝率）
        critical_reject_rate = self._stats.get_reject_rate(RequestPriority.CRITICAL)

        if critical_reject_rate > 0.1:  # 拒绝率超过 10%
            old_threshold = self.config.critical_backpressure_threshold
            self.config.critical_backpressure_threshold = min(
                self.config.critical_backpressure_threshold + 0.05,
                0.95
            )
            if self.config.critical_backpressure_threshold != old_threshold:
                logger.info(
                    f"Auto-adjust: CRITICAL backpressure_threshold increased to "
                    f"{self.config.critical_backpressure_threshold:.2f}"
                )

        # 3. 普通队列调整
        normal_avg_wait = self._stats.get_avg_wait_time(RequestPriority.NORMAL)
        if normal_avg_wait > self.config.normal_target_wait_time:
            old_rate = self.config.normal_dispatch_rate
            self.config.normal_dispatch_rate *= 1.2
            self.config.normal_dispatch_rate = min(self.config.normal_dispatch_rate, 5.0)

            if self.config.normal_dispatch_rate != old_rate:
                logger.info(
                    f"Auto-adjust: NORMAL dispatch_rate increased to "
                    f"{self.config.normal_dispatch_rate:.2f}"
                )

    def get_stats(self) -> Dict[str, Any]:
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
                "critical_target_wait_time": self.config.critical_target_wait_time,
                "normal_max_size": self.config.normal_max_size,
                "normal_backpressure_threshold": self.config.normal_backpressure_threshold,
                "normal_dispatch_rate": self.config.normal_dispatch_rate,
                "normal_target_wait_time": self.config.normal_target_wait_time,
                "auto_adjust_enabled": self.config.auto_adjust_enabled,
            },
            "stats": self._stats.get_stats_dict(),
            "running": self._running,
        }