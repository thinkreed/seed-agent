"""后台任务生命周期管理模块

包含任务注册、启动、完成、失败、超时方法。
"""

import logging
import threading
from datetime import UTC, datetime
from typing import Any

from src.abort_signal import AbortController
from src.background_task_registry._types import BackgroundTaskEntry, TaskStatus

logger = logging.getLogger(__name__)


class LifecycleMixin:
    """任务生命周期方法 mixin

    提供 register, start, complete, fail, timeout 方法。
    需要 _tasks 和 _lock 属性。
    """

    _tasks: dict[str, BackgroundTaskEntry]
    _lock: threading.Lock

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
            entry.started_at = datetime.now(UTC)

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
            entry.completed_at = datetime.now(UTC)
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
            entry.completed_at = datetime.now(UTC)
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
            entry.completed_at = datetime.now(UTC)
            entry.error = "Task execution timeout"

            logger.warning(f"Task timeout: id={task_id}")
            return True


__all__ = ["LifecycleMixin"]