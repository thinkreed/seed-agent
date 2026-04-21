"""LLM 请求队列系统

实现异步请求调度、优先级队列和反压机制
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Deque, Optional, Callable, Any, List
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum

logger = logging.getLogger("seed_agent")


class RequestPriority(IntEnum):
    """请求优先级"""
    CRITICAL = 0    # 用户直接交互，跳过队列
    HIGH = 1        # RalphLoop 迭代，优先处理
    NORMAL = 2      # Subagent 任务，标准处理
    LOW = 3         # Scheduler 后台，队列处理


@dataclass
class RequestItem:
    """队列中的请求项"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    model_id: str = ""
    messages: List[Dict] = field(default_factory=list)
    kwargs: Dict = field(default_factory=dict)
    priority: RequestPriority = RequestPriority.NORMAL
    created_at: float = field(default_factory=time.time)

    # 结果存储
    result: Optional[Dict] = None
    error: Optional[Exception] = None
    completed: bool = False

    # 等待事件
    _completion_event: asyncio.Event = field(default_factory=asyncio.Event)


class QueueFullError(Exception):
    """队列已满异常"""
    pass


class RequestQueue:
    """请求队列系统

    特性:
    - 多优先级队列
    - FIFO + 优先级排序
    - 异步调度分发
    - 反压机制（队列满时拒绝新请求）
    """

    def __init__(
        self,
        max_size: int = 50,
        dispatch_rate: float = 0.33,
        backpressure_threshold: float = 0.8,
    ):
        """
        Args:
            max_size: 队列最大容量
            dispatch_rate: 调度速率（requests/sec）
            backpressure_threshold: 反压阈值（0.0-1.0）
        """
        self.max_size = max_size
        self.dispatch_rate = dispatch_rate
        self.backpressure_threshold = backpressure_threshold

        # 多优先级队列
        self._queues: Dict[RequestPriority, Deque[RequestItem]] = {
            p: deque() for p in RequestPriority
        }

        # 结果存储
        self._results: Dict[str, RequestItem] = {}

        # 调度控制
        self._dispatcher_task: Optional[asyncio.Task] = None
        self._executor: Optional[Callable] = None
        self._new_request_event = asyncio.Event()
        self._running = False
        self._lock = asyncio.Lock()

        # 统计
        self._total_submitted = 0
        self._total_completed = 0
        self._total_rejected = 0

    def get_fill_ratio(self) -> float:
        """获取队列填充率"""
        total = sum(len(q) for q in self._queues.values())
        return total / self.max_size

    def get_queue_size(self) -> int:
        """获取当前队列大小"""
        return sum(len(q) for q in self._queues.values())

    async def submit(
        self,
        model_id: str,
        messages: List[Dict],
        priority: RequestPriority = RequestPriority.NORMAL,
        **kwargs
    ) -> str:
        """提交请求到队列

        Args:
            model_id: 模型 ID
            messages: 消息列表
            priority: 请求优先级
            **kwargs: 其他参数

        Returns:
            request_id: 请求 ID

        Raises:
            QueueFullError: 队列已满
        """
        # 反压检查
        fill_ratio = self.get_fill_ratio()
        if fill_ratio >= self.backpressure_threshold:
            self._total_rejected += 1
            raise QueueFullError(
                f"Queue at {fill_ratio:.1%} capacity (threshold: {self.backpressure_threshold:.1%}), "
                f"rejecting requests"
            )

        item = RequestItem(
            model_id=model_id,
            messages=messages,
            kwargs=kwargs,
            priority=priority,
        )

        async with self._lock:
            self._queues[priority].append(item)
            self._results[item.id] = item
            self._total_submitted += 1

        self._new_request_event.set()

        logger.debug(f"Request {item.id} submitted with priority {priority.name}")
        return item.id

    async def wait_for_result(
        self,
        request_id: str,
        timeout: float = 300.0
    ) -> Dict:
        """等待请求完成

        Args:
            request_id: 请求 ID
            timeout: 最大等待时间（秒）

        Returns:
            请求结果

        Raises:
            TimeoutError: 等待超时
            Exception: 请求执行失败
        """
        if request_id not in self._results:
            raise ValueError(f"Unknown request ID: {request_id}")

        item = self._results[request_id]

        try:
            await asyncio.wait_for(item._completion_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Request {request_id} timed out after {timeout}s")

        if item.error:
            raise item.error

        return item.result

    async def start_dispatcher(self, executor: Callable):
        """启动异步调度器

        Args:
            executor: 执行函数，签名: async fn(model_id, messages, **kwargs) -> Dict
        """
        if self._running:
            logger.warning("Dispatcher already running")
            return

        self._executor = executor
        self._running = True
        self._dispatcher_task = asyncio.create_task(self._dispatch_loop())
        logger.info(f"Request queue dispatcher started (rate: {self.dispatch_rate} req/sec)")

    async def stop_dispatcher(self):
        """停止调度器"""
        self._running = False
        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
        logger.info("Request queue dispatcher stopped")

    async def _dispatch_loop(self):
        """调度循环核心"""
        while self._running:
            try:
                # 等待新请求
                await self._new_request_event.wait()

                # 获取下一个请求
                item = await self._get_next_request()
                if not item:
                    self._new_request_event.clear()
                    continue

                # 创建执行任务
                asyncio.create_task(self._execute_request(item))

                # 控制调度速率
                await asyncio.sleep(1.0 / self.dispatch_rate)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Dispatch loop error: {e}")
                await asyncio.sleep(1.0)

    async def _get_next_request(self) -> Optional[RequestItem]:
        """按优先级获取下一个请求"""
        async with self._lock:
            for priority in RequestPriority:
                if self._queues[priority]:
                    return self._queues[priority].popleft()
        return None

    async def _execute_request(self, item: RequestItem):
        """执行单个请求"""
        try:
            logger.debug(f"Executing request {item.id} (priority: {item.priority.name})")

            result = await self._executor(
                item.model_id,
                item.messages,
                item.priority,
                **item.kwargs
            )

            item.result = result
            item.completed = True
            self._total_completed += 1

            logger.debug(f"Request {item.id} completed successfully")

        except Exception as e:
            item.error = e
            item.completed = True
            logger.error(f"Request {item.id} failed: {e}")

        finally:
            item._completion_event.set()

            # 清理旧结果（保留最近 100 个）
            if len(self._results) > 100:
                async with self._lock:
                    # 只保留未完成的和最近完成的
                    to_remove = []
                    for rid, ritem in self._results.items():
                        if ritem.completed and ritem.id != item.id:
                            age = time.time() - ritem.created_at
                            if age > 300:  # 5 分钟前的已完成请求
                                to_remove.append(rid)
                    for rid in to_remove:
                        self._results.pop(rid, None)

    def get_stats(self) -> Dict[str, Any]:
        """获取队列统计信息"""
        return {
            "queue_size": self.get_queue_size(),
            "fill_ratio": self.get_fill_ratio(),
            "max_size": self.max_size,
            "backpressure_threshold": self.backpressure_threshold,
            "dispatch_rate": self.dispatch_rate,
            "total_submitted": self._total_submitted,
            "total_completed": self._total_completed,
            "total_rejected": self._total_rejected,
            "pending_by_priority": {
                p.name: len(self._queues[p]) for p in RequestPriority
            },
            "running": self._running,
        }

    async def cancel_request(self, request_id: str) -> bool:
        """取消请求

        Args:
            request_id: 请求 ID

        Returns:
            是否成功取消
        """
        async with self._lock:
            # 从队列中移除
            for priority in RequestPriority:
                for i, item in enumerate(self._queues[priority]):
                    if item.id == request_id:
                        self._queues[priority].remove(item)
                        item.error = asyncio.CancelledError("Request cancelled")
                        item.completed = True
                        item._completion_event.set()
                        return True

        # 可能正在执行中
        if request_id in self._results:
            item = self._results[request_id]
            if not item.completed:
                # 标记为取消（执行中的无法真正中断）
                item.error = asyncio.CancelledError("Request cancelled during execution")
                return False

        return False

    async def clear_queue(self):
        """清空队列"""
        async with self._lock:
            for priority in RequestPriority:
                while self._queues[priority]:
                    item = self._queues[priority].popleft()
                    item.error = asyncio.CancelledError("Queue cleared")
                    item.completed = True
                    item._completion_event.set()

        logger.info("Request queue cleared")