"""定时任务管理模块：Agent 自主创建和管理定时任务

参考 GenericAgent scheduler.py 设计
任务存储路径从 PathsConfig 动态获取

此模块作为 facade，从 scheduler/ 子包导入所有功能以保持向后兼容。
"""

# 从 scheduler 子包导入所有功能
from src.scheduler import (
    ScheduledTask,
    TaskScheduler,
    _get_tasks_dir,
    _get_tasks_file,
    create_scheduled_task,
    get_task_info,
    list_scheduled_tasks,
    register_scheduler_tools,
    remove_scheduled_task,
)

__all__ = [
    "TaskScheduler",
    "ScheduledTask",
    "create_scheduled_task",
    "remove_scheduled_task",
    "list_scheduled_tasks",
    "get_task_info",
    "register_scheduler_tools",
    "_get_tasks_dir",
    "_get_tasks_file",
]