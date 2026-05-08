"""TaskStop 工具函数

提取 task_stop, task_status, list_tasks, cancel_all_tasks。
"""

import logging

from src.background_task_registry import (
    CANCEL_GRACE_SECONDS,
    TaskStatus,
    get_background_task_registry,
)

logger = logging.getLogger(__name__)


def task_stop(task_id: str) -> str:
    """停止后台任务"""
    registry = get_background_task_registry()

    status = registry.get_status(task_id)
    if not status:
        return f"Error: Task '{task_id}' not found"

    if status == TaskStatus.COMPLETED:
        return f"Task '{task_id}' is already completed"
    if status == TaskStatus.FAILED:
        return f"Task '{task_id}' has already failed"
    if status == TaskStatus.CANCELLED:
        return f"Task '{task_id}' is already cancelled"
    if status == TaskStatus.TIMEOUT:
        return f"Task '{task_id}' has already timed out"

    if status == TaskStatus.PENDING:
        registry.cancel(task_id)
        return f"Task '{task_id}' cancelled (was pending)"

    success = registry.cancel(task_id)

    if success:
        return f"Task '{task_id}' cancellation initiated. Will complete within {CANCEL_GRACE_SECONDS}s grace period."
    return f"Failed to cancel task '{task_id}'"


def task_status(task_id: str) -> str:
    """查询任务状态"""
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
        result += f"Result: {(entry.result or '')[:200]}...\n"

    if entry.error:
        result += f"Error: {entry.error}\n"

    return result


def list_tasks(status: str | None = None) -> str:
    """列出所有任务"""
    registry = get_background_task_registry()

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

    stats = registry.get_stats()
    result += f"\nStatistics: total={stats['total']}, running={stats['running']}, pending={stats['pending']}"

    return result


def cancel_all_tasks() -> str:
    """取消所有运行中的任务"""
    registry = get_background_task_registry()
    count = registry.cancel_all()

    return f"Cancelled {count} tasks"


__all__ = ["task_stop", "task_status", "list_tasks", "cancel_all_tasks"]