"""
Subagent 工具集 - 为 AgentLoop 提供 Subagent 操作接口

核心工具:
- spawn_subagent: 创建并启动子代理
- wait_for_subagent: 等待子代理完成
- aggregate_subagent_results: 聚合多个子代理结果
- list_subagents: 列出所有子代理状态
- kill_subagent: 终止子代理
"""

import asyncio
import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.subagent_manager import SubagentManager

logger = logging.getLogger(__name__)

# 全局 SubagentManager 实例（由 AgentLoop 初始化时注入）
_subagent_manager: "SubagentManager | None" = None

# 后台任务集合（防止 asyncio.create_task 返回值被垃圾回收）
_background_tasks: set[asyncio.Task[None]] = set()
_MAX_BACKGROUND_TASKS = 100  # 最大后台任务数，防止内存泄漏


def _add_background_task(task: asyncio.Task[None]) -> None:
    """安全添加后台任务，超过限制时清理已完成任务"""
    # 如果超过最大限制，清理已完成任务
    if len(_background_tasks) >= _MAX_BACKGROUND_TASKS:
        done_tasks = [t for t in _background_tasks if t.done()]
        for t in done_tasks:
            _background_tasks.discard(t)
        if done_tasks:
            logger.debug(f"Cleaned {len(done_tasks)} completed background tasks")

    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# 线程安全锁（保护全局状态）
_manager_lock = threading.Lock()


def init_subagent_manager(manager):
    """初始化全局 SubagentManager"""
    global _subagent_manager
    _subagent_manager = manager


def spawn_subagent(
    type: str,
    prompt: str,
    custom_tools: list[str] | None = None,
    timeout: int | None = None,
) -> str:
    """
    创建并启动一个子代理任务。

    Args:
        type: 子代理类型 - 'explore', 'review', 'implement', 'plan'
        prompt: 任务提示，描述子代理需要完成的工作
        custom_tools: 自定义工具列表（可选，覆盖默认权限集）
        timeout: 执行超时时间（秒），默认根据任务类型动态配置 (180s-900s)

    Returns:
        任务 ID，用于后续跟踪和等待
    """
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    from src.subagent import SubagentType

    # 转换类型
    type_map = {
        "explore": SubagentType.EXPLORE,
        "review": SubagentType.REVIEW,
        "implement": SubagentType.IMPLEMENT,
        "plan": SubagentType.PLAN,
    }

    subagent_type = type_map.get(type.lower())
    if subagent_type is None:
        return f"Error: Unknown subagent type '{type}'. Supported: explore, review, implement, plan"

    # 创建任务
    custom_tools_set = set(custom_tools) if custom_tools else None
    task_id = _subagent_manager.create_task(
        subagent_type=subagent_type,
        prompt=prompt,
        custom_tools=custom_tools_set,
        timeout=timeout,
    )

    # 尝试启动异步执行（仅在事件循环存在时）
    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(_run_subagent_async(task_id))
        _add_background_task(task)
    except RuntimeError:
        # 没有运行的事件循环，任务只创建不启动
        # 在 AgentLoop 异步环境中会正常启动
        logger.debug(f"No event loop, task {task_id} created but not started")

    logger.info(f"Spawned subagent {task_id} (type={type})")
    return f"Subagent task created: {task_id}\nType: {type}\nStatus: pending\nUse 'wait_for_subagent' to get results."


async def _run_subagent_async(task_id: str):
    """异步执行 subagent"""
    if _subagent_manager is None:
        logger.error(f"SubagentManager not initialized, cannot run {task_id}")
        return
    try:
        await _subagent_manager.run_subagent(task_id)
    except Exception as e:
        logger.error(f"Subagent {task_id} execution error: {e}")


async def wait_for_subagent_async(
    task_id: str,
    timeout: float | None = None,
) -> str:
    """
    等待子代理完成并返回结果（异步版本）。

    Args:
        task_id: 要等待的任务 ID
        timeout: 等待超时时间（秒），None 表示无限等待

    Returns:
        任务执行结果或错误信息
    """
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    result = _subagent_manager.get_result(task_id)
    if result:
        # 任务已完成
        return result.summary

    # 等待任务完成
    try:
        if timeout:
            # 使用 asyncio.wait_for 设置超时
            async def wait_loop():
                while True:
                    res = _subagent_manager.get_result(task_id)
                    if res:
                        return res
                    await asyncio.sleep(0.5)

            result = await asyncio.wait_for(wait_loop(), timeout=timeout)
        else:
            # 无限等待
            while True:
                res = _subagent_manager.get_result(task_id)
                if res:
                    result = res
                    break
                await asyncio.sleep(0.5)

        return result.summary if result else f"Error: No result for task {task_id}"

    except asyncio.TimeoutError:
        return f"Error: Timeout waiting for subagent {task_id}"
    except Exception as e:
        return f"Error: {e!s}"


def wait_for_subagent(
    task_id: str,
    timeout: float | None = None,
) -> str:
    """
    等待子代理完成并返回结果（同步包装）。

    注意：这个工具在 AgentLoop 的异步上下文中运行，
    实际执行会通过 _execute_tool_calls 中的异步处理完成。

    Args:
        task_id: 要等待的任务 ID
        timeout: 等待超时时间（秒）

    Returns:
        任务执行结果或状态信息
    """
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    result = _subagent_manager.get_result(task_id)
    if result:
        return result.summary

    status = _subagent_manager.get_status(task_id)
    if status is None:
        return f"Error: Task {task_id} not found"

    return (f"Task {task_id} status: {status}\n"
            f"Result not yet available. "
            f"Use 'wait_for_subagent_async' or check again later.")


def aggregate_subagent_results(
    task_ids: list[str],
    include_errors: bool = True,
    max_length: int = 2000,
) -> str:
    """
    聚合多个子代理的执行结果。

    Args:
        task_ids: 任务 ID 列表
        include_errors: 是否包含失败任务的错误信息，默认 True
        max_length: 单个结果的最大显示长度，默认 2000

    Returns:
        聚合后的结果摘要
    """
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    return _subagent_manager.aggregate_results(
        task_ids=task_ids,
        include_errors=include_errors,
        max_length=max_length,
    )


def list_subagents(status: str | None = None) -> str:
    """
    列出所有子代理任务及其状态。

    Args:
        status: 过滤特定状态（可选） - 'pending', 'running', 'completed', 'failed', 'timeout'

    Returns:
        任务列表，包含 ID、类型、状态和提示预览
    """
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    tasks = _subagent_manager.list_tasks(status=status)

    if not tasks:
        return "No subagent tasks found."

    lines = ["Subagent Tasks:"]
    for task in tasks:
        lines.append(
            f"  [{task['id']}] {task['type']} - {task['status']}\n"
            f"    Prompt: {task['prompt_preview']}"
        )

    return "\n".join(lines)


def kill_subagent(task_id: str) -> str:
    """
    终止一个子代理任务。

    Args:
        task_id: 要终止的任务 ID

    Returns:
        操作结果
    """
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    status = _subagent_manager.get_status(task_id)
    if status is None:
        return f"Error: Task {task_id} not found"

    if status == "completed":
        return f"Task {task_id} already completed. No need to kill."

    # 清理任务资源
    _subagent_manager.cleanup(task_id)
    logger.info(f"Killed subagent {task_id}")

    return f"Subagent {task_id} terminated and resources cleaned up."


def get_subagent_status(task_id: str) -> str:
    """
    获取单个子代理的详细状态。

    Args:
        task_id: 任务 ID

    Returns:
        详细状态信息，包含执行次数、耗时等
    """
    if _subagent_manager is None:
        return "Error: SubagentManager not initialized"

    result = _subagent_manager.get_result(task_id)
    if result:
        return f"Task {task_id}:\n" + result.summary + f"\n\nDetails: {result.to_dict()}"

    status = _subagent_manager.get_status(task_id)
    if status is None:
        return f"Error: Task {task_id} not found"

    return f"Task {task_id} status: {status}"


def spawn_parallel_subagents(
    tasks: list[dict],
) -> str:
    """
    创建并并行启动多个子代理任务。

    Args:
        tasks: 任务列表，每个任务包含:
            - type: 子代理类型 ('explore', 'review', 'implement', 'plan')
            - prompt: 任务提示
            - timeout: 可选超时时间

    Returns:
        创建的任务 ID 列表和启动信息
    """
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
            return f"Error: Unknown type '{type_str}' in task spec"

        task_id = _subagent_manager.create_task(
            subagent_type=subagent_type,
            prompt=task_spec.get("prompt", ""),
            timeout=task_spec.get("timeout", 300),
        )
        task_ids.append(task_id)

    # 尝试并行启动所有任务（仅在事件循环存在时）
    try:
        asyncio.get_running_loop()
        task = asyncio.create_task(_run_parallel_async(task_ids))
        _add_background_task(task)
    except RuntimeError:
        # 没有运行的事件循环，任务只创建不启动
        logger.debug(f"No event loop, {len(task_ids)} tasks created but not started")

    return f"Created {len(task_ids)} subagent tasks:\n" + "\n".join(task_ids)


async def _run_parallel_async(task_ids: list[str]):
    """异步并行执行多个 subagent"""
    if _subagent_manager is None:
        logger.error("SubagentManager not initialized, cannot run parallel")
        return
    try:
        await _subagent_manager.run_parallel(task_ids)
    except Exception as e:
        logger.error(f"Parallel execution error: {e}")


def register_subagent_tools(registry):
    """注册 Subagent 工具到 Registry"""
    # 注册同步工具（返回状态或需要异步等待的提示）
    registry.register("spawn_subagent", spawn_subagent)
    registry.register("wait_for_subagent", wait_for_subagent)
    registry.register("aggregate_subagent_results", aggregate_subagent_results)
    registry.register("list_subagents", list_subagents)
    registry.register("kill_subagent", kill_subagent)
    registry.register("get_subagent_status", get_subagent_status)
    registry.register("spawn_parallel_subagents", spawn_parallel_subagents)

    # 注册异步工具（实际异步执行）
    registry.register("wait_for_subagent_async", wait_for_subagent_async)
