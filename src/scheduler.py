"""定时任务管理模块：Agent 自主创建和管理定时任务

参考 GenericAgent scheduler.py 设计
任务存储在 ~/.seed/tasks/ 目录
"""

import os
import json
import time
import logging
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Callable
from datetime import datetime
from request_queue import RequestPriority

logger = logging.getLogger("seed_agent")

# 任务存储路径
TASKS_DIR = Path(os.path.expanduser("~")) / ".seed" / "tasks"
TASKS_FILE = TASKS_DIR / "scheduled_tasks.json"


class ScheduledTask:
    """定时任务定义"""

    def __init__(
        self,
        task_id: str,
        task_type: str,
        interval_seconds: int,
        prompt: str,
        last_run: float = 0,
        enabled: bool = True
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.interval_seconds = interval_seconds
        self.prompt = prompt
        self.last_run = last_run
        self.enabled = enabled

    def should_run(self) -> bool:
        """检查是否应该执行"""
        if not self.enabled:
            return False
        return time.time() - self.last_run >= self.interval_seconds

    def mark_run(self):
        """标记已执行"""
        self.last_run = time.time()

    def to_dict(self) -> Dict:
        """序列化"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "interval_seconds": self.interval_seconds,
            "prompt": self.prompt,
            "last_run": self.last_run,
            "enabled": self.enabled
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ScheduledTask':
        """反序列化"""
        return cls(
            task_id=data["task_id"],
            task_type=data["task_type"],
            interval_seconds=data["interval_seconds"],
            prompt=data["prompt"],
            last_run=data.get("last_run", 0),
            enabled=data.get("enabled", True)
        )


class TaskScheduler:
    """定时任务调度器"""

    # 内置任务类型及其默认间隔
    BUILTIN_TASKS = {
        "autodream": 12 * 60 * 60,  # 每12小时记忆整理
        "health_check": 60 * 60,  # 每小时健康检查
    }

    def __init__(self, agent_loop=None):
        self.agent = agent_loop
        self._tasks: Dict[str, ScheduledTask] = {}
        self._running: bool = False
        self._check_interval: int = 60  # 每60秒检查一次
        self._task: Optional[asyncio.Task] = None
        self._load_tasks()
        self._init_builtin_tasks()

    def _load_tasks(self):
        """加载已保存的任务"""
        TASKS_DIR.mkdir(parents=True, exist_ok=True)

        if TASKS_FILE.exists():
            with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for task_data in data.get("tasks", []):
                    task = ScheduledTask.from_dict(task_data)
                    self._tasks[task.task_id] = task
            logger.info(f"Loaded {len(self._tasks)} scheduled tasks")

    def _save_tasks(self):
        """保存任务到文件"""
        TASKS_DIR.mkdir(parents=True, exist_ok=True)

        data = {
            "updated_at": datetime.now().isoformat(),
            "tasks": [t.to_dict() for t in self._tasks.values()]
        }

        with open(TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved {len(self._tasks)} scheduled tasks")

    def _init_builtin_tasks(self):
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
                enabled=True
            )
            modified = True

        # 2. health_check: 系统健康检查
        if "health_check" not in self._tasks:
            self._tasks["health_check"] = ScheduledTask(
                task_id="health_check",
                task_type="custom",
                interval_seconds=self.BUILTIN_TASKS["health_check"],
                prompt="运行诊断脚本 `python scripts/diagnose_seed_agent.py --json -q`，统计 FAIL/WARN。如有 FAIL，尝试修复。将结果摘要追加到任务日志。",
                last_run=now,  # 启动时设置，避免立即触发
                enabled=True
            )
            modified = True
            
        if modified:
            self._save_tasks()

    async def start(self):
        """启动调度器"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._schedule_loop())
        logger.info("Task scheduler started")

    async def stop(self):
        """停止调度器"""
        self._running = False
        self._save_tasks()

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Task scheduler stopped")

    async def _schedule_loop(self):
        """调度循环"""
        while self._running:
            await self._check_and_run_tasks()
            await asyncio.sleep(self._check_interval)

    async def _check_and_run_tasks(self):
        """检查并执行到期任务"""
        for task_id, task in self._tasks.items():
            if task.should_run():
                logger.info(f"Task {task_id} triggered, executing...")
                await self._execute_task(task)
                task.mark_run()
                self._save_tasks()

    async def _execute_task(self, task: ScheduledTask):
        """执行任务（支持 tool_calls 循环处理）
        
        使用 LOW 优先级，确保定时任务不会阻塞用户请求。
        用户请求使用 CRITICAL 优先级，会立即执行。
        """
        try:
            if not self.agent:
                logger.warning(f"No agent available for task {task.task_id}")
                self._log_task_execution(task, "No agent available", success=False)
                return

            # 使用 agent 的 run 处理任务，支持 tool_calls 循环
            # 使用 LOW 优先级，确保定时任务入队等待，不阻塞用户请求
            original_max_iterations = self.agent.max_iterations

            try:
                # 临时提升迭代次数以支持复杂任务
                self.agent.max_iterations = max(original_max_iterations, 30)

                # 通过 run 执行任务（自动处理 tool_calls 循环）
                # LOW 优先级会入队等待，让用户请求（CRITICAL）优先执行
                response = await self.agent.run(task.prompt, priority=RequestPriority.LOW)

                # 记录执行结果
                if response:
                    logger.info(f"Task {task.task_id} completed ({len(response)} chars)")
                else:
                    logger.warning(f"Task {task.task_id} returned empty response")

                # 记录执行日志
                result = response[:500] if response else "Empty response"
                self._log_task_execution(task, result, success=bool(response))

            finally:
                # 恢复原始迭代限制
                self.agent.max_iterations = original_max_iterations

        except Exception as e:
            logger.exception(f"Task {task.task_id} failed: {e}")
            self._log_task_execution(task, f"Error: {str(e)}", success=False)

    def _log_task_execution(self, task: ScheduledTask, result: str, success: bool = True):
        """记录任务执行日志"""
        log_file = TASKS_DIR / "execution_log.jsonl"

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "task_id": task.task_id,
            "task_type": task.task_type,
            "success": success,
            "result": result[:500]
        }

        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    def add_task(
        self,
        task_id: str,
        task_type: str,
        interval_seconds: int,
        prompt: str
    ) -> str:
        """
        添加自定义定时任务

        Args:
            task_id: 任务唯一标识
            task_type: 任务类型（autodream/custom）
            interval_seconds: 执行间隔（秒）
            prompt: 执行时的 prompt

        Returns:
            操作结果
        """
        if task_id in self._tasks:
            return f"Task {task_id} already exists"

        self._tasks[task_id] = ScheduledTask(
            task_id=task_id,
            task_type=task_type,
            interval_seconds=interval_seconds,
            prompt=prompt,
            enabled=True
        )

        self._save_tasks()
        logger.info(f"Added task {task_id} (interval: {interval_seconds}s)")

        return f"Task {task_id} added successfully, will run every {interval_seconds} seconds"

    def remove_task(self, task_id: str) -> str:
        """
        移除定时任务

        Args:
            task_id: 任务ID

        Returns:
            操作结果
        """
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
            next_run = "disabled" if not task.enabled else f"{task.interval_seconds}s interval"
            lines.append(f"  {task_id}: {task.task_type} | {next_run} | {task.prompt[:50]}...")

        return '\n'.join(lines)

    def get_task_status(self, task_id: str) -> Dict:
        """获取任务状态"""
        if task_id not in self._tasks:
            return {"error": "Task not found"}

        task = self._tasks[task_id]
        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "interval_seconds": task.interval_seconds,
            "enabled": task.enabled,
            "last_run": datetime.fromtimestamp(task.last_run).isoformat() if task.last_run > 0 else "never",
            "next_run_in": task.interval_seconds - (time.time() - task.last_run) if task.enabled else "disabled"
        }


# 工具函数（供 agent 调用）
def create_scheduled_task(task_id: str, interval_minutes: int, prompt: str) -> str:
    """
    Create a scheduled task that runs periodically.

    Args:
        task_id: Unique task identifier (e.g., 'daily_cleanup')
        interval_minutes: Interval in minutes (e.g., 60 for hourly)
        prompt: Prompt to execute when task triggers

    Returns:
        Success message or error.
    """
    scheduler = TaskScheduler()
    return scheduler.add_task(
        task_id=task_id,
        task_type="custom",
        interval_seconds=interval_minutes * 60,
        prompt=prompt
    )


def remove_scheduled_task(task_id: str) -> str:
    """
    Remove a scheduled task.

    Args:
        task_id: Task ID to remove

    Returns:
        Success message or error.
    """
    scheduler = TaskScheduler()
    return scheduler.remove_task(task_id)


def list_scheduled_tasks() -> str:
    """
    List all scheduled tasks.

    Returns:
        Formatted list of tasks.
    """
    scheduler = TaskScheduler()
    return scheduler.list_tasks()


def get_task_info(task_id: str) -> str:
    """
    Get detailed info about a scheduled task.

    Args:
        task_id: Task ID to query

    Returns:
        Task status information.
    """
    scheduler = TaskScheduler()
    status = scheduler.get_task_status(task_id)
    if "error" in status:
        return status["error"]

    return json.dumps(status, ensure_ascii=False, indent=2)


def register_scheduler_tools(registry):
    """注册定时任务工具"""
    registry.register("create_scheduled_task", create_scheduled_task)
    registry.register("remove_scheduled_task", remove_scheduled_task)
    registry.register("list_scheduled_tasks", list_scheduled_tasks)
    registry.register("get_task_info", get_task_info)