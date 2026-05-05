"""后台任务查询模块

包含任务状态查询、列表、统计等方法。
"""

import logging
import threading
from typing import Any

from src.abort_signal import AbortController
from src.background_task_registry._types import BackgroundTaskEntry, TaskStatus

logger = logging.getLogger(__name__)


class QueryMixin:
    """任务查询方法 mixin

    提供 get_status, get_entry, get_abort_controller, list_tasks, 
    get_running_count, can_start_new, cleanup, get_stats 方法。
    需要 _tasks, _lock, _max_concurrent 属性。
    """

    _tasks: dict[str, BackgroundTaskEntry]
    _lock: threading.Lock
    _max_concurrent: int

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
        result = [
            entry.to_dict()
            for entry in self._tasks.values()
            if status is None or entry.status == status
        ]

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


__all__ = ["QueryMixin"]