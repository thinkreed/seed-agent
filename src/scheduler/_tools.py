"""定时任务工具函数模块

包含供 agent 调用的工具函数：
- create_scheduled_task
- remove_scheduled_task
- list_scheduled_tasks
- get_task_info
- register_scheduler_tools
"""

import json

from src.tools import ToolRegistry

# 模块级单例引用（由 _scheduler.py 设置）
_scheduler_instance = None


def _get_scheduler():
    """获取 TaskScheduler 实例"""
    global _scheduler_instance
    if _scheduler_instance is None:
        from src.scheduler._scheduler import TaskScheduler
        _scheduler_instance = TaskScheduler()
    return _scheduler_instance


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
    "_get_scheduler",
    "create_scheduled_task",
    "get_task_info",
    "list_scheduled_tasks",
    "register_scheduler_tools",
    "remove_scheduled_task",
]