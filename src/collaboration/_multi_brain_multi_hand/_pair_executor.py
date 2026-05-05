"""组合执行器模块

负责单个 Claude+Sandbox 组合的执行逻辑
"""

import json
import logging
from typing import Any

from src.collaboration._types import AgentInstance

logger = logging.getLogger(__name__)


async def execute_pair(
    agent: AgentInstance,
    task: str,
    session_state: dict[str, Any],
    other_agents: list[AgentInstance],
) -> dict[str, Any]:
    """单个组合执行

    Args:
        agent: 智能体实例
        task: 任务描述
        session_state: Session 状态
        other_agents: 其他智能体列表（用于构建上下文）

    Returns:
        执行结果
    """
    agent.status = "running"

    # 构建上下文
    context = build_pair_context(task, session_state, other_agents)

    # Claude 推理
    try:
        response = await agent.llm_client.reason(context)

        # Sandbox 执行工具
        tool_results: list[str] = []
        tool_calls = (
            response.get("choices", [{}])[0].get("message", {}).get("tool_calls")
        )

        if tool_calls and agent.sandbox:
            results = await agent.sandbox.execute_tools(tool_calls)
            tool_results = [r.get("content", "") for r in results]

        agent.status = "completed"

        return {
            "pair_id": agent.id,
            "response": response,
            "tool_results": tool_results,
            "status": "completed",
        }

    except Exception as e:
        logger.exception(f"Pair {agent.id} execution failed")
        agent.status = "failed"
        return {
            "pair_id": agent.id,
            "error": str(e),
            "status": "failed",
        }


def build_pair_context(
    task: str,
    session_state: dict[str, Any],
    other_agents: list[AgentInstance],
) -> list[dict[str, Any]]:
    """构建组合上下文

    Args:
        task: 任务描述
        session_state: Session 状态
        other_agents: 其他智能体列表

    Returns:
        上下文消息列表
    """
    # 包含任务和其他组合的进度
    other_pairs_progress = [
        {"pair_id": agent.id, "status": agent.status}
        for agent in other_agents
        if agent.id != session_state.get("current_pair_id")
    ]

    return [
        {
            "role": "system",
            "content": "你是一个协作智能体，正在与其他智能体协同完成任务。",
        },
        {
            "role": "user",
            "content": f"""任务: {task}

其他智能体状态:
{json.dumps(other_pairs_progress, ensure_ascii=False, indent=2)}

请执行你的部分任务，并输出结果或下一步建议。
""",
        },
    ]


async def execute_assignments(
    assignments: dict[str, list[dict]],
    agents: list[AgentInstance],
) -> list[dict[str, Any]]:
    """执行分配的任务

    Args:
        assignments: 任务分配字典
        agents: 智能体列表

    Returns:
        执行结果列表
    """
    results: list[dict[str, Any]] = []

    for pair_id, tasks in assignments.items():
        # 找到对应的智能体
        agent = next((a for a in agents if a.id == pair_id), None)
        if not agent:
            results.append(
                {
                    "pair_id": pair_id,
                    "status": "failed",
                    "error": "Agent not found",
                }
            )
            continue

        # 执行任务
        for task_item in tasks:
            result = await execute_pair(
                agent,
                task_item.get("task", ""),
                {},
                agents,
            )
            results.append(result)

    return results