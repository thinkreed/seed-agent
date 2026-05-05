"""定时任务管理方法模块

包含 TaskScheduler 的任务管理相关方法：
- add_task
- remove_task
- disable_task
- enable_task
- list_tasks
- get_task_status
"""

import logging
import time
from datetime import UTC, datetime

from src.scheduler._task_definition import ScheduledTask

logger = logging.getLogger("seed_agent")


class TaskManagementMixin:
    """任务管理方法 mixin

    提供 add_task, remove_task, disable_task, enable_task, list_tasks, get_task_status 方法。
    需要 _tasks 和 _save_tasks 方法。
    """

    _tasks: dict[str, ScheduledTask]
    BUILTIN_TASKS: dict[str, int]

    def _save_tasks(self) -> None:
        """保存任务（由 TaskScheduler 提供）"""
        raise NotImplementedError

    def add_task(
        self, task_id: str, task_type: str, interval_seconds: int, prompt: str
    ) -> str:
        """添加自定义定时任务"""
        if task_id in self._tasks:
            return f"Task {task_id} already exists"

        self._tasks[task_id] = ScheduledTask(
            task_id=task_id,
            task_type=task_type,
            interval_seconds=interval_seconds,
            prompt=prompt,
            enabled=True,
        )

        self._save_tasks()
        logger.info(f"Added task {task_id} (interval: {interval_seconds}s)")

        return f"Task {task_id} added successfully, will run every {interval_seconds} seconds"

    def remove_task(self, task_id: str) -> str:
        """移除定时任务"""
        if task_id not in self._tasks:
            return f"Task {task_id} not found"

        # 不允许移除内置任务
        if task_id in self.BUILTIN_TASKS:
            return f"Cannot remove builtin task {task_id}, use disable instead"

        del self._tasks[task_id]
        self._save_tasks()

        return f"Task {task_id} removed"

    def disable_task(self, task_id: str) -> str:
        """禁用任务"""
        if task_id not in self._tasks:
            return f"Task {task_id} not found"

        self._tasks[task_id].enabled = False
        self._save_tasks()

        return f"Task {task_id} disabled"

    def enable_task(self, task_id: str) -> str:
        """启用任务"""
        if task_id not in self._tasks:
            return f"Task {task_id} not found"

        self._tasks[task_id].enabled = True
        self._save_tasks()

        return f"Task {task_id} enabled"

    def list_tasks(self) -> str:
        """列出所有任务"""
        if not self._tasks:
            return "No scheduled tasks"

        lines = ["Scheduled Tasks:", "-" * 40]
        for task_id, task in self._tasks.items():
            next_run = (
                "disabled" if not task.enabled else f"{task.interval_seconds}s interval"
            )
            lines.append(
                f"  {task_id}: {task.task_type} | {next_run} | {task.prompt[:50]}..."
            )

        return "\n".join(lines)

    def get_task_status(self, task_id: str) -> dict:
        """获取任务状态"""
        if task_id not in self._tasks:
            return {"error": "Task not found"}

        task = self._tasks[task_id]
        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "interval_seconds": task.interval_seconds,
            "enabled": task.enabled,
            "last_run": datetime.fromtimestamp(task.last_run, tz=UTC).isoformat()
            if task.last_run > 0
            else "never",
            "next_run_in": task.interval_seconds - (time.time() - task.last_run)
            if task.enabled
            else "disabled",
        }


__all__ = ["TaskManagementMixin"]