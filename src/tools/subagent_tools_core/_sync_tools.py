"""
Subagent 同步工具模块 - 创建类工具

提供工具：spawn_subagent, spawn_parallel_subagents
操作类工具从 _sync_tools_ops 导入并重导出
"""
import asyncio
import logging
from typing import TYPE_CHECKING

from src.tools.utils import add_background_task, safe_int_convert

if TYPE_CHECKING:
    from src.subagent_manager import SubagentManager

logger = logging.getLogger(__name__)
_subagent_manager: "SubagentManager | None" = None


def init_subagent_manager(manager: "SubagentManager") -> None:
    """初始化全局 SubagentManager"""
    global _subagent_manager
    _subagent_manager = manager


_TYPE_MAP = None


def _get_type_map():
    """获取类型映射（延迟导入避免循环依赖）"""
    global _TYPE_MAP
    if _TYPE_MAP is None:
        from src.subagent import SubagentType
        _TYPE_MAP = {
            "explore": SubagentType.EXPLORE,
            "review": SubagentType.REVIEW,
            "implement": SubagentType.IMPLEMENT,
            "plan": SubagentType.PLAN,
        }
    return _TYPE_MAP


def spawn_subagent(
    subagent_type: str,
    prompt: str,
    custom_tools: list[str] | None = None,
    timeout: int | None = None,
) -> str:
    """创建并启动一个子代理任务"""
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    type_map = _get_type_map()
    resolved_type = type_map.get(subagent_type.lower())
    if resolved_type is None:
        return f"Error: Unknown subagent type '{subagent_type}'"

    safe_timeout = (
        safe_int_convert(timeout, default=300, min_val=1)
        if timeout is not None else None
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


def spawn_parallel_subagents(tasks: list[dict]) -> str:
    """创建并并行启动多个子代理任务"""
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    type_map = _get_type_map()
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


# 从 _sync_tools_ops 导入操作类工具并重导出
from ._sync_tools_ops import (
    aggregate_subagent_results,
    get_subagent_status,
    kill_subagent,
    list_subagents,
    wait_for_subagent,
)