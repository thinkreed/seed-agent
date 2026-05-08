"""
TaskStop 工具模块

基于 qwen-code 的 task-stop.ts 设计。

聚合工具函数和注册逻辑。
"""

import logging

from src.tools._task_stop_tools import (
    cancel_all_tasks,
    list_tasks,
    task_status,
    task_stop,
)

logger = logging.getLogger(__name__)


def register_task_stop_tools(registry) -> None:
    """注册 TaskStop 相关工具"""
    registry.register("task_stop", task_stop)
    registry.register("task_status", task_status)
    registry.register("list_tasks", list_tasks)
    registry.register("cancel_all_tasks", cancel_all_tasks)

    logger.info(
        "TaskStop tools registered: task_stop, task_status, list_tasks, cancel_all_tasks"
    )


__all__ = [
    "task_stop",
    "task_status",
    "list_tasks",
    "cancel_all_tasks",
    "register_task_stop_tools",
]