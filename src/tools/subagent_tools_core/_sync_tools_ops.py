"""
Subagent 同步操作工具模块

提供查询和操作类工具：
- wait_for_subagent: 等待子代理完成
- aggregate_subagent_results: 聚合结果
- list_subagents: 列出子代理状态
- kill_subagent: 终止子代理
- get_subagent_status: 获取详细状态

依赖:
- 从 _sync_tools 导入全局 _subagent_manager
"""

import logging

from src.tools.utils import safe_int_convert

logger = logging.getLogger(__name__)

# 延迟导入避免循环依赖
def _get_manager():
    """获取全局 SubagentManager"""
    from ._sync_tools import _subagent_manager
    return _subagent_manager


def wait_for_subagent(task_id: str, timeout: float | None = None) -> str:
    """等待子代理完成（同步包装）"""
    _subagent_manager = _get_manager()
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    result = _subagent_manager.get_result(task_id)
    if result:
        return result.summary

    status = _subagent_manager.get_status(task_id)
    if status is None:
        return f"Error: Task {task_id} not found"

    return f"Task {task_id} status: {status}\nResult not yet available."


def aggregate_subagent_results(
    task_ids: list[str],
    include_errors: bool = True,
    max_length: int = 2000,
) -> str:
    """聚合多个子代理的执行结果"""
    _subagent_manager = _get_manager()
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    safe_max_length = safe_int_convert(max_length, default=2000, min_val=1)

    return _subagent_manager.aggregate_results(
        task_ids=task_ids,
        include_errors=include_errors,
        max_length=safe_max_length,
    )


def list_subagents(status: str | None = None) -> str:
    """列出所有子代理任务及其状态"""
    _subagent_manager = _get_manager()
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    tasks = _subagent_manager.list_tasks(status=status)

    if not tasks:
        return "No subagent tasks found."

    lines = ["Subagent Tasks:"]
    lines.extend(
        f"  [{task['id']}] {task['type']} - {task['status']}\n"
        f"    Prompt: {task['prompt_preview']}"
        for task in tasks
    )

    return "\n".join(lines)


def kill_subagent(task_id: str) -> str:
    """终止一个子代理任务"""
    _subagent_manager = _get_manager()
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    status = _subagent_manager.get_status(task_id)
    if status is None:
        return f"Error: Task {task_id} not found"

    if status == "completed":
        return f"Task {task_id} already completed."

    _subagent_manager.cleanup(task_id)
    logger.info(f"Killed subagent {task_id}")

    return f"Subagent {task_id} terminated."


def get_subagent_status(task_id: str) -> str:
    """获取单个子代理的详细状态"""
    _subagent_manager = _get_manager()
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    result = _subagent_manager.get_result(task_id)
    if result:
        return f"Task {task_id}:\n{result.summary}\n\nDetails: {result.to_dict()}"

    status = _subagent_manager.get_status(task_id)
    if status is None:
        return f"Error: Task {task_id} not found"

    return f"Task {task_id} status: {status}"