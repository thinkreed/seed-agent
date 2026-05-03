"""
TaskStop 工具模块

基于 qwen-code 的 task-stop.ts 设计：
- 停止后台任务执行
- 优雅取消机制
- 状态查询

核心特性：
- 任务 ID 识别
- 取消信号发送
- 优雅期等待
- 状态反馈

参考：
- qwen-code: task-stop.ts
"""

import logging
from typing import Optional

from src.background_task_registry import (
    BackgroundTaskRegistry,
    TaskStatus,
    CANCEL_GRACE_SECONDS,
    get_background_task_registry,
)

logger = logging.getLogger(__name__)


def task_stop(task_id: str) -> str:
    """停止后台任务

    Args:
        task_id: 要停止的任务 ID

    Returns:
        操作结果信息
    """
    registry = get_background_task_registry()

    status = registry.get_status(task_id)
    if not status:
        return f"Error: Task '{task_id}' not found"

    if status == TaskStatus.COMPLETED:
        return f"Task '{task_id}' is already completed"
    elif status == TaskStatus.FAILED:
        return f"Task '{task_id}' has already failed"
    elif status == TaskStatus.CANCELLED:
        return f"Task '{task_id}' is already cancelled"
    elif status == TaskStatus.TIMEOUT:
        return f"Task '{task_id}' has already timed out"

    if status == TaskStatus.PENDING:
        # 任务尚未开始，直接取消
        registry.cancel(task_id)
        return f"Task '{task_id}' cancelled (was pending)"

    # 任务正在运行，触发取消
    success = registry.cancel(task_id)

    if success:
        return (
            f"Task '{task_id}' cancellation initiated. "
            f"Will complete within {CANCEL_GRACE_SECONDS}s grace period."
        )
    else:
        return f"Failed to cancel task '{task_id}'"


def task_status(task_id: str) -> str:
    """查询任务状态

    Args:
        task_id: 任务 ID

    Returns:
        任务状态信息
    """
    registry = get_background_task_registry()

    entry = registry.get_entry(task_id)
    if not entry:
        return f"Task '{task_id}' not found"

    status_info = entry.to_dict()

    result = f"Task '{task_id}' status: {status_info['status']}\n"
    result += f"Created: {status_info['created_at']}\n"

    if status_info.get("started_at"):
        result += f"Started: {status_info['started_at']}\n"

    if status_info.get("completed_at"):
        result += f"Completed: {status_info['completed_at']}\n"

    if entry.result:
        result += f"Result: {entry.result[:200]}...\n"

    if entry.error:
        result += f"Error: {entry.error}\n"

    return result


def list_tasks(status: Optional[str] = None) -> str:
    """列出所有任务

    Args:
        status: 过滤状态（可选：pending, running, completed, failed, cancelled, timeout）

    Returns:
        任务列表信息
    """
    registry = get_background_task_registry()

    # 转换状态字符串
    filter_status = None
    if status:
        try:
            filter_status = TaskStatus(status.lower())
        except ValueError:
            return f"Error: Invalid status '{status}'. Valid values: pending, running, completed, failed, cancelled, timeout"

    tasks = registry.list_tasks(status=filter_status)

    if not tasks:
        status_str = f" with status '{status}'" if status else ""
        return f"No tasks found{status_str}"

    result = f"Found {len(tasks)} tasks:\n"
    for task in tasks:
        result += f"- {task['task_id']}: {task['status']} (created: {task['created_at']})\n"

    # 添加统计
    stats = registry.get_stats()
    result += f"\nStatistics: total={stats['total']}, running={stats['running']}, pending={stats['pending']}"

    return result


def cancel_all_tasks() -> str:
    """取消所有运行中的任务

    Returns:
        操作结果信息
    """
    registry = get_background_task_registry()
    count = registry.cancel_all()

    return f"Cancelled {count} tasks"


def register_task_stop_tools(registry) -> None:
    """注册 TaskStop 相关工具

    Args:
        registry: ToolRegistry 实例
    """
    registry.register("task_stop", task_stop)
    registry.register("task_status", task_status)
    registry.register("list_tasks", list_tasks)
    registry.register("cancel_all_tasks", cancel_all_tasks)

    logger.info("TaskStop tools registered: task_stop, task_status, list_tasks, cancel_all_tasks")