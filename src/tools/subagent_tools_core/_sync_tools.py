"""
Subagent 同步工具模块

提供同步风格的 Subagent 工具：
- spawn_subagent: 创建子代理
- wait_for_subagent: 等待子代理完成
- aggregate_subagent_results: 聚合结果
- list_subagents: 列出子代理状态
- kill_subagent: 终止子代理
- get_subagent_status: 获取详细状态
- spawn_parallel_subagents: 并行创建多个子代理

类型安全:
- 所有数值参数强制转换为整数
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from src.tools.utils import add_background_task, safe_int_convert

if TYPE_CHECKING:
    from src.subagent_manager import SubagentManager

logger = logging.getLogger(__name__)

# 全局 SubagentManager 实例
_subagent_manager: "SubagentManager | None" = None


def init_subagent_manager(manager: "SubagentManager") -> None:
    """初始化全局 SubagentManager"""
    global _subagent_manager
    _subagent_manager = manager


def spawn_subagent(
    subagent_type: str,
    prompt: str,
    custom_tools: list[str] | None = None,
    timeout: int | None = None,
) -> str:
    """创建并启动一个子代理任务"""
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    from src.subagent import SubagentType

    type_map = {
        "explore": SubagentType.EXPLORE,
        "review": SubagentType.REVIEW,
        "implement": SubagentType.IMPLEMENT,
        "plan": SubagentType.PLAN,
    }

    resolved_type = type_map.get(subagent_type.lower())
    if resolved_type is None:
        return f"Error: Unknown subagent type '{subagent_type}'"

    safe_timeout = (
        safe_int_convert(timeout, default=300, min_val=1)
        if timeout is not None
        else None
    )

    custom_tools_set = set(custom_tools) if custom_tools else None
    task_id = _subagent_manager.create_task(
        subagent_type=resolved_type,
        prompt=prompt,
        custom_tools=custom_tools_set,
        timeout=safe_timeout,
    )

    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(_run_subagent_async(task_id))
        add_background_task(task)
    except RuntimeError:
        logger.debug(f"No event loop, task {task_id} created but not started")

    logger.info(f"Spawned subagent {task_id} (type={subagent_type})")
    return f"Subagent task created: {task_id}\nType: {subagent_type}\nStatus: pending"


def wait_for_subagent(task_id: str, timeout: float | None = None) -> str:
    """等待子代理完成（同步包装）"""
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
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    result = _subagent_manager.get_result(task_id)
    if result:
        return f"Task {task_id}:\n{result.summary}\n\nDetails: {result.to_dict()}"

    status = _subagent_manager.get_status(task_id)
    if status is None:
        return f"Error: Task {task_id} not found"

    return f"Task {task_id} status: {status}"


def spawn_parallel_subagents(tasks: list[dict]) -> str:
    """创建并并行启动多个子代理任务"""
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    from src.subagent import SubagentType

    type_map = {
        "explore": SubagentType.EXPLORE,
        "review": SubagentType.REVIEW,
        "implement": SubagentType.IMPLEMENT,
        "plan": SubagentType.PLAN,
    }

    task_ids = []
    for task_spec in tasks:
        type_str = task_spec.get("type", "explore").lower()
        subagent_type = type_map.get(type_str)
        if subagent_type is None:
            return f"Error: Unknown type '{type_str}'"

        raw_timeout = task_spec.get("timeout", 300)
        safe_timeout = safe_int_convert(raw_timeout, default=300, min_val=1)

        task_id = _subagent_manager.create_task(
            subagent_type=subagent_type,
            prompt=task_spec.get("prompt", ""),
            timeout=safe_timeout,
        )
        task_ids.append(task_id)

    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(_run_parallel_async(task_ids))
        add_background_task(task)
    except RuntimeError:
        logger.debug(f"No event loop, {len(task_ids)} tasks created but not started")

    return f"Created {len(task_ids)} subagent tasks:\n" + "\n".join(task_ids)


# === 内部异步执行函数 ===


async def _run_subagent_async(task_id: str):
    """异步执行 subagent"""
    if _subagent_manager is None:
        logger.error(f"SubagentManager not initialized, cannot run {task_id}")
        return
    try:
        await _subagent_manager.run_subagent(task_id)
    except Exception as e:
        logger.exception(f"Subagent {task_id} execution error: {e}")


async def _run_parallel_async(task_ids: list[str]):
    """异步并行执行多个 subagent"""
    if _subagent_manager is None:
        logger.error("SubagentManager not initialized")
        return
    try:
        await _subagent_manager.run_parallel(task_ids)
    except Exception as e:
        logger.exception(f"Parallel execution error: {e}")