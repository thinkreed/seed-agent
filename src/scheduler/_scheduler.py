"""定时任务调度器核心模块

包含 TaskScheduler 类和工具函数。
"""

import asyncio
import contextlib
import json
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.scheduler._execution import execute_task, log_task_execution
from src.scheduler._storage import (
    _get_tasks_dir,
    _get_tasks_file,
    load_tasks,
    save_tasks,
)
from src.scheduler._task_definition import ScheduledTask
from src.tools import ToolRegistry

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

logger = logging.getLogger("seed_agent")


# 模块级单例：避免工具函数重复创建实例
_global_scheduler: "TaskScheduler | None" = None


def _get_scheduler() -> "TaskScheduler":
    """获取全局 TaskScheduler 单例（延迟初始化）"""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = TaskScheduler()
    return _global_scheduler


class TaskScheduler:
    """定时任务调度器"""

    # 内置任务类型及其默认间隔
    BUILTIN_TASKS = {
        "autodream": 12 * 60 * 60,  # 每12小时记忆整理
    }

    def __init__(self, agent_loop: "AgentLoop | None" = None) -> None:
        self.agent = agent_loop
        self._tasks: dict[str, ScheduledTask] = {}
        self._running: bool = False
        self._check_interval: int = 60  # 每60秒检查一次
        self._task: asyncio.Task | None = None
        self._load_tasks()
        self._init_builtin_tasks()

    def _load_tasks(self) -> None:
        """加载已保存的任务"""
        tasks_file = _get_tasks_file()
        data = load_tasks(tasks_file)

        for task_data in data.get("tasks", []):
            try:
                task = ScheduledTask.from_dict(task_data)
                self._tasks[task.task_id] = task
            except (KeyError, TypeError) as e:
                logger.warning(
                    f"Skipping invalid task data: {task_data}, error: {e}"
                )
        logger.info(f"Loaded {len(self._tasks)} scheduled tasks")

    def _save_tasks(self) -> None:
        """保存任务到文件"""
        tasks_file = _get_tasks_file()
        tasks_data = {"tasks": [t.to_dict() for t in self._tasks.values()]}
        save_tasks(tasks_data, tasks_file)

    def _init_builtin_tasks(self) -> None:
        """初始化内置任务

        重要：启动时设置 last_run 为当前时间，避免立即触发到期的任务。
        这样确保任务在启动后等待一个完整间隔周期才首次执行。
        """
        modified = False
        now = time.time()

        # 1. autodream: 记忆整理
        if "autodream" not in self._tasks:
            self._tasks["autodream"] = ScheduledTask(
                task_id="autodream",
                task_type="autodream",
                interval_seconds=self.BUILTIN_TASKS["autodream"],
                prompt="执行 autodream 记忆整理 SOP：分层逐查、ROI评估、低ROI清理、补全高价值项",
                last_run=now,  # 启动时设置，避免立即触发
                enabled=True,
            )
            modified = True

        if modified:
            self._save_tasks()

    async def start(self) -> None:
        """启动调度器"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._schedule_loop())
        logger.info("Task scheduler started")

    async def stop(self) -> None:
        """停止调度器"""
        self._running = False
        self._save_tasks()

        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

        logger.info("Task scheduler stopped")

    async def _schedule_loop(self) -> None:
        """调度循环"""
        while self._running:
            await self._check_and_run_tasks()
            await asyncio.sleep(self._check_interval)

    async def _check_and_run_tasks(self) -> None:
        """检查并执行到期任务"""
        for task_id, task in self._tasks.items():
            if task.should_run():
                logger.info(f"Task {task_id} triggered, executing...")
                success, result = await execute_task(self.agent, task)
                log_task_execution(task, result, success)
                task.mark_run()
                self._save_tasks()

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


# 工具函数（供 agent 调用）
def create_scheduled_task(task_id: str, interval_minutes: int, prompt: str) -> str:
    """Create a scheduled task that runs periodically."""
    return _get_scheduler().add_task(
        task_id=task_id,
        task_type="custom",
        interval_seconds=interval_minutes * 60,
        prompt=prompt,
    )


def remove_scheduled_task(task_id: str) -> str:
    """Remove a scheduled task."""
    return _get_scheduler().remove_task(task_id)


def list_scheduled_tasks() -> str:
    """List all scheduled tasks."""
    return _get_scheduler().list_tasks()


def get_task_info(task_id: str) -> str:
    """Get detailed info about a scheduled task."""
    status = _get_scheduler().get_task_status(task_id)
    if "error" in status:
        return status["error"]

    return json.dumps(status, ensure_ascii=False, indent=2)


def register_scheduler_tools(registry: ToolRegistry) -> None:
    """注册定时任务工具"""
    registry.register("create_scheduled_task", create_scheduled_task)
    registry.register("remove_scheduled_task", remove_scheduled_task)
    registry.register("list_scheduled_tasks", list_scheduled_tasks)
    registry.register("get_task_info", get_task_info)


__all__ = [
    "TaskScheduler",
    "_get_scheduler",
    "create_scheduled_task",
    "remove_scheduled_task",
    "list_scheduled_tasks",
    "get_task_info",
    "register_scheduler_tools",
]