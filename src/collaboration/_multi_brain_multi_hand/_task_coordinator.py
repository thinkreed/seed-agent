"""任务协调模块

负责动态任务分配和重新分配
"""

import logging
from typing import Any

from src.collaboration._types import AgentInstance
from src.session_event_stream import EventType

logger = logging.getLogger(__name__)

# 默认配置
MAX_DYNAMIC_ITERATIONS = 10  # 动态任务分配最大迭代


async def initial_assignment(
    task: str,
    pair_ids: list[str],
) -> dict[str, list[dict]]:
    """初始任务分配

    Args:
        task: 任务描述
        pair_ids: 组合 ID 列表

    Returns:
        任务分配字典
    """
    # 简化：将任务平均分配给各组合
    assignments: dict[str, list[dict]] = {}

    for pair_id in pair_ids:
        assignments[pair_id] = [{"task": task, "phase": "initial"}]

    return assignments


async def reassign_tasks(
    remaining_task: str,
    completed_pairs: list[str],
    remaining_pairs: list[str],
    session: Any,
) -> dict[str, list[dict]]:
    """重新分配任务

    Args:
        remaining_task: 剩余任务
        completed_pairs: 已完成的组合
        remaining_pairs: 待完成的组合
        session: SessionEventStream 实例

    Returns:
        新的分配方案
    """
    # 获取已完成的结果作为上下文
    completed_results = [
        e["data"].get("result")
        for e in session.get_events()
        if e["type"] == EventType.SUBAGENT_RESULT.value
        and e["data"].get("pair_id") in completed_pairs
    ]

    # 新分配
    assignments: dict[str, list[dict]] = {}
    for pair_id in remaining_pairs:
        assignments[pair_id] = [
            {
                "task": remaining_task,
                "context": completed_results,
                "phase": "reassigned",
            }
        ]

    return assignments


async def dynamic_task_assignment(
    task: str,
    pair_ids: list[str],
    agents: list[AgentInstance],
    session: Any,
    execute_assignments_func: Any,
) -> dict[str, Any]:
    """动态任务分配

    根据执行进度动态调整任务分配

    Args:
        task: 任务描述
        pair_ids: 组合 ID 列表
        agents: 智能体列表
        session: SessionEventStream 实例
        execute_assignments_func: 执行分配的函数

    Returns:
        分配结果
    """
    # 1. 初始分配
    initial_assignments = await initial_assignment(task, pair_ids)

    # 2. 执行监控
    final_results: list[dict[str, Any]] = []
    iteration = 0

    while iteration < MAX_DYNAMIC_ITERATIONS:
        iteration += 1

        # 执行当前分配
        results = await execute_assignments_func(initial_assignments, agents)
        final_results = results

        # 检查完成状态
        completed_pairs = [
            r["pair_id"] for r in results if r.get("status") == "completed"
        ]

        if len(completed_pairs) == len(pair_ids):
            break

        # 3. 动态重分配
        remaining_pairs = [
            pid for pid in pair_ids if pid not in completed_pairs
        ]

        if remaining_pairs:
            initial_assignments = await reassign_tasks(
                task, completed_pairs, remaining_pairs, session
            )

    return {
        "task": task,
        "initial_assignments": initial_assignments,
        "final_results": final_results,
        "iterations": iteration,
        "completed": len(
            [r for r in final_results if r.get("status") == "completed"]
        ),
    }