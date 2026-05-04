"""
后台任务注册表模块

基于 qwen-code 的 background-tasks.ts 设计：
- 每个后台任务关联一个 AbortController
- cancel() 发送取消信号
- 优雅期让自然完成优先
- 状态持久化和恢复

核心特性：
- 任务生命周期管理
- 取消信号传播
- 优雅期竞争处理
- 任务状态查询

参考：
- qwen-code: background-tasks.ts
"""

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from src.abort_signal import AbortController

logger = logging.getLogger(__name__)

# 优雅等待期（秒）
CANCEL_GRACE_SECONDS = 5


class TaskStatus(Enum):
    """任务状态"""

    PENDING = "pending"  # 等待执行
    RUNNING = "running"  # 正在执行
    COMPLETED = "completed"  # 执行完成
    FAILED = "failed"  # 执行失败
    CANCELLED = "cancelled"  # 已取消
    TIMEOUT = "timeout"  # 执行超时


@dataclass
class BackgroundTaskEntry:
    """后台任务条目"""

    task_id: str
    prompt: str
    status: TaskStatus
    abort_controller: AbortController
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "prompt": self.prompt[:100] + "..."
            if len(self.prompt) > 100
            else self.prompt,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "result": self.result[:200] + "..."
            if self.result and len(self.result) > 200
            else self.result,
            "error": self.error,
        }


class BackgroundTaskRegistry:
    """后台任务注册表

    参考 qwen-code 的 background-tasks.ts 实现

    核心功能：
    - 任务注册和生命周期管理
    - 取消信号传播
    - 优雅期等待
    - 状态查询

    使用示例：
        registry = BackgroundTaskRegistry()

        # 注册任务
        entry = registry.register("task_123", "Long running task")

        # 开始执行
        registry.start("task_123")

        # 取消任务
        registry.cancel("task_123")

        # 查询状态
        status = registry.get_status("task_123")
    """

    def __init__(self, max_concurrent: int = 3):
        """初始化注册表

        Args:
            max_concurrent: 最大并发任务数
        """
        self._tasks: dict[str, BackgroundTaskEntry] = {}
        self._max_concurrent = max_concurrent
        # 使用线程锁保护并发访问（兼容同步方法）
        self._lock = threading.Lock()
        # 异步锁用于异步方法
        self._async_lock = asyncio.Lock()

        logger.info(
            f"BackgroundTaskRegistry initialized: max_concurrent={max_concurrent}"
        )

    def register(
        self,
        task_id: str,
        prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> BackgroundTaskEntry:
        """注册新任务（线程安全）

        Args:
            task_id: 任务唯一 ID
            prompt: 任务描述/提示
            metadata: 额外元数据

        Returns:
            任务条目
        """
        with self._lock:
            entry = BackgroundTaskEntry(
                task_id=task_id,
                prompt=prompt,
                status=TaskStatus.PENDING,
                abort_controller=AbortController(),
                metadata=metadata or {},
            )
            self._tasks[task_id] = entry

            logger.info(f"Task registered: id={task_id}, prompt={prompt[:50]}...")
            return entry

    def start(self, task_id: str) -> bool:
        """标记任务开始执行（线程安全）

        Args:
            task_id: 任务 ID

        Returns:
            是否成功标记
        """
        with self._lock:
            entry = self._tasks.get(task_id)
            if not entry:
                logger.warning(f"Task not found: {task_id}")
                return False

            if entry.status != TaskStatus.PENDING:
                logger.warning(
                    f"Task {task_id} is not pending (status={entry.status.value})"
                )
                return False

            entry.status = TaskStatus.RUNNING
            entry.started_at = datetime.now()

            logger.info(f"Task started: id={task_id}")
            return True

    def complete(self, task_id: str, result: str) -> bool:
        """标记任务完成（线程安全）

        Args:
            task_id: 任务 ID
            result: 执行结果

        Returns:
            是否成功标记
        """
        with self._lock:
            entry = self._tasks.get(task_id)
            if not entry:
                return False

            entry.status = TaskStatus.COMPLETED
            entry.completed_at = datetime.now()
            entry.result = result

            logger.info(f"Task completed: id={task_id}")
            return True

    def fail(self, task_id: str, error: str) -> bool:
        """标记任务失败（线程安全）

        Args:
            task_id: 任务 ID
            error: 错误信息

        Returns:
            是否成功标记
        """
        with self._lock:
            entry = self._tasks.get(task_id)
            if not entry:
                return False

            entry.status = TaskStatus.FAILED
            entry.completed_at = datetime.now()
            entry.error = error

            logger.warning(f"Task failed: id={task_id}, error={error[:100]}")
            return True

    def timeout(self, task_id: str) -> bool:
        """标记任务超时（线程安全）

        Args:
            task_id: 任务 ID

        Returns:
            是否成功标记
        """
        with self._lock:
            entry = self._tasks.get(task_id)
            if not entry:
                return False

            entry.status = TaskStatus.TIMEOUT
            entry.completed_at = datetime.now()
            entry.error = "Task execution timeout"

            logger.warning(f"Task timeout: id={task_id}")
            return True

    def cancel(self, task_id: str) -> bool:
        """取消任务（线程安全）

        发送取消信号并启动优雅等待期。
        自然完成处理器通常会赢得竞争。

        Args:
            task_id: 任务 ID

        Returns:
            是否成功触发取消
        """
        with self._lock:
            entry = self._tasks.get(task_id)
            if not entry:
                logger.warning(f"Task not found for cancel: {task_id}")
                return False

            if entry.status != TaskStatus.RUNNING:
                logger.warning(
                    f"Task {task_id} is not running (status={entry.status.value})"
                )
                # 直接标记为取消
                if entry.status == TaskStatus.PENDING:
                    entry.status = TaskStatus.CANCELLED
                    entry.completed_at = datetime.now()
                    entry.error = "Cancelled before execution"
                return False

            # 触发 abort 信号
            entry.abort_controller.abort(reason="user_cancelled")

        # 设置优雅等待期（在锁外执行异步任务）
        asyncio.create_task(self._grace_period_handler(task_id))

        logger.info(f"Task cancellation initiated: id={task_id}")
        return True

    async def _grace_period_handler(self, task_id: str) -> None:
        """优雅等待期处理（线程安全）

        在优雅期内，如果任务自然完成，则保持完成状态。
        如果超过优雅期仍未完成，则强制标记为取消。
        """
        await asyncio.sleep(CANCEL_GRACE_SECONDS)

        with self._lock:
            entry = self._tasks.get(task_id)
            if entry and entry.status == TaskStatus.RUNNING:
                # 超过优雅期，强制取消
                entry.status = TaskStatus.CANCELLED
                entry.completed_at = datetime.now()
                entry.error = "Cancelled after grace period"

                logger.info(f"Task force cancelled after grace period: id={task_id}")

    def cancel_all(self) -> int:
        """取消所有运行中的任务（线程安全）

        Returns:
            取消的任务数量
        """
        tasks_to_cancel: list[str] = []

        with self._lock:
            for task_id, entry in self._tasks.items():
                if entry.status == TaskStatus.RUNNING:
                    tasks_to_cancel.append(task_id)
                elif entry.status == TaskStatus.PENDING:
                    # 直接标记为取消
                    entry.status = TaskStatus.CANCELLED
                    entry.completed_at = datetime.now()
                    entry.error = "Cancelled before execution"

        # 在锁外执行取消（避免死锁）
        for task_id in tasks_to_cancel:
            self.cancel(task_id)

        logger.info(f"Cancelled {len(tasks_to_cancel)} running tasks")
        return len(tasks_to_cancel)

    def get_status(self, task_id: str) -> TaskStatus | None:
        """获取任务状态

        Args:
            task_id: 任务 ID

        Returns:
            任务状态，或 None（任务不存在）
        """
        entry = self._tasks.get(task_id)
        return entry.status if entry else None

    def get_entry(self, task_id: str) -> BackgroundTaskEntry | None:
        """获取任务条目

        Args:
            task_id: 任务 ID

        Returns:
            任务条目，或 None
        """
        return self._tasks.get(task_id)

    def get_abort_controller(self, task_id: str) -> AbortController | None:
        """获取任务的取消控制器

        Args:
            task_id: 任务 ID

        Returns:
            AbortController，或 None
        """
        entry = self._tasks.get(task_id)
        return entry.abort_controller if entry else None

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """列出任务

        Args:
            status: 过滤状态（可选）
            limit: 最大返回数量

        Returns:
            任务列表
        """
        result = []
        for entry in self._tasks.values():
            if status is None or entry.status == status:
                result.append(entry.to_dict())

        # 按创建时间排序，最新的在前
        result.sort(key=lambda x: x["created_at"], reverse=True)
        return result[:limit]

    def get_running_count(self) -> int:
        """获取正在运行的任务数量"""
        return sum(
            1 for entry in self._tasks.values() if entry.status == TaskStatus.RUNNING
        )

    def can_start_new(self) -> bool:
        """是否可以启动新任务"""
        return self.get_running_count() < self._max_concurrent

    def cleanup(self, task_id: str | None = None) -> int:
        """清理任务资源（线程安全）

        Args:
            task_id: 指定清理的任务 ID，None 表示清理所有已完成任务

        Returns:
            清理的任务数量
        """
        if task_id:
            with self._lock:
                if task_id in self._tasks:
                    del self._tasks[task_id]
                    logger.debug(f"Task cleaned up: id={task_id}")
                    return 1
            return 0

        # 清理所有已完成的任务
        to_remove: list[str] = []
        with self._lock:
            for tid, entry in self._tasks.items():
                if entry.status in (
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                    TaskStatus.TIMEOUT,
                ):
                    to_remove.append(tid)

            for tid in to_remove:
                del self._tasks[tid]

        logger.info(f"Cleaned up {len(to_remove)} tasks")
        return len(to_remove)

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息"""
        stats = {
            "total": len(self._tasks),
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "timeout": 0,
        }
        for entry in self._tasks.values():
            stats[entry.status.value] += 1

        return stats


# 全局注册表
_global_registry: BackgroundTaskRegistry | None = None


def get_background_task_registry() -> BackgroundTaskRegistry:
    """获取全局后台任务注册表"""
    global _global_registry
    if _global_registry is None:
        _global_registry = BackgroundTaskRegistry()
    return _global_registry


def init_background_task_registry(
    max_concurrent: int = 3,
) -> BackgroundTaskRegistry:
    """初始化全局注册表

    Args:
        max_concurrent: 最大并发任务数

    Returns:
        注册表实例
    """
    global _global_registry
    _global_registry = BackgroundTaskRegistry(max_concurrent=max_concurrent)
    return _global_registry


def reset_background_task_registry() -> None:
    """重置全局注册表"""
    global _global_registry
    if _global_registry:
        _global_registry.cancel_all()
        _global_registry.cleanup()
    _global_registry = BackgroundTaskRegistry()
