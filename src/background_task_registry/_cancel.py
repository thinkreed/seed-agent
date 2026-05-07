"""后台任务取消模块

包含任务取消和取消所有运行任务的方法。
"""

import asyncio
import logging
import threading
from datetime import UTC, datetime

from src.background_task_registry._types import (
    CANCEL_GRACE_SECONDS,
    BackgroundTaskEntry,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class CancelMixin:
    """任务取消方法 mixin

    提供 cancel, cancel_all, _grace_period_handler 方法。
    需要 _tasks 和 _lock 属性。
    """

    _tasks: dict[str, BackgroundTaskEntry]
    _lock: threading.Lock

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
                    entry.completed_at = datetime.now(UTC)
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
                entry.completed_at = datetime.now(UTC)
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
                    entry.completed_at = datetime.now(UTC)
                    entry.error = "Cancelled before execution"

        # 在锁外执行取消（避免死锁）
        for task_id in tasks_to_cancel:
            self.cancel(task_id)

        logger.info(f"Cancelled {len(tasks_to_cancel)} running tasks")
        return len(tasks_to_cancel)


__all__ = ["CancelMixin"]