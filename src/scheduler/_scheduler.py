"""定时任务调度器核心模块

包含 TaskScheduler 类定义和主调度逻辑。
"""

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING

from src.scheduler._execution import execute_task, log_task_execution
from src.scheduler._storage import load_tasks, save_tasks
from src.scheduler._task_definition import ScheduledTask
from src.scheduler._task_management import TaskManagementMixin

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

logger = logging.getLogger("seed_agent")


class TaskScheduler(TaskManagementMixin):
    """定时任务调度器"""

    BUILTIN_TASKS = {"autodream": 12 * 60 * 60}

    def __init__(self, agent_loop: "AgentLoop | None" = None) -> None:
        self.agent = agent_loop
        self._tasks: dict[str, ScheduledTask] = {}
        self._running: bool = False
        self._check_interval: int = 60
        self._task: asyncio.Task | None = None
        self._load_tasks()
        self._init_builtin_tasks()

    def _load_tasks(self) -> None:
        """加载已保存的任务"""
        # 动态获取 tasks_file 以支持测试 mock
        from src.scheduler._storage import _get_tasks_file
        tasks_file = _get_tasks_file()
        data = load_tasks(tasks_file)

        for task_data in data.get("tasks", []):
            try:
                task = ScheduledTask.from_dict(task_data)
                self._tasks[task.task_id] = task
            except (KeyError, TypeError) as e:
                logger.warning(f"Skipping invalid task data: {task_data}, error: {e}")
        logger.info(f"Loaded {len(self._tasks)} scheduled tasks")

    def _save_tasks(self) -> None:
        """保存任务到文件"""
        # 动态获取 tasks_file 以支持测试 mock
        from src.scheduler._storage import _get_tasks_file
        tasks_file = _get_tasks_file()
        tasks_data = {"tasks": [t.to_dict() for t in self._tasks.values()]}
        save_tasks(tasks_data, tasks_file)

    def _init_builtin_tasks(self) -> None:
        """初始化内置任务"""
        modified = False
        now = time.time()

        if "autodream" not in self._tasks:
            self._tasks["autodream"] = ScheduledTask(
                task_id="autodream",
                task_type="autodream",
                interval_seconds=self.BUILTIN_TASKS["autodream"],
                prompt="执行 autodream 记忆整理 SOP：分层逐查、ROI评估、低ROI清理、补全高价值项",
                last_run=now,
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


__all__ = ["TaskScheduler"]