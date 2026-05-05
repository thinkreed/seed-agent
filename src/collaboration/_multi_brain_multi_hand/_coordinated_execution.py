"""协调执行模块

执行协调任务的核心逻辑
"""

import asyncio
import logging
from typing import Any

from src.collaboration._multi_brain_multi_hand._pair_executor import execute_pair
from src.collaboration._multi_brain_multi_hand._result_merger import merge_from_session
from src.collaboration._types import CoordinationResult
from src.session_event_stream import EventType

logger = logging.getLogger(__name__)


async def coordinated_execution(
    session: Any,
    agents: list[Any],
    pair_ids: list[str],
    task: str,
) -> CoordinationResult:
    """协调执行

    流程:
    1. Session 记录任务
    2. 各组合独立执行
    3. 结果记录到 Session
    4. Session 协调合并

    Args:
        session: SessionEventStream 实例
        agents: 智能体实例列表
        pair_ids: 组合 ID 列表
        task: 任务描述

    Returns:
        协调结果
    """
    # 1. Session 记录任务
    session.emit_event(
        EventType.SESSION_START,
        {
            "task": task,
            "pairs": pair_ids,
            "mode": "multi_brain_multi_hand",
        },
    )

    # 2. 各组合独立执行（并行）
    pair_results = await asyncio.gather(
        *[execute_pair(agent, task, {}, agents) for agent in agents],
        return_exceptions=True,
    )

    # 3. 结果记录到 Session
    processed_results: list[dict[str, Any]] = []
    for pair_id, result in zip(pair_ids, pair_results, strict=True):
        if isinstance(result, Exception):
            session.emit_event(
                EventType.ERROR_OCCURRED,
                {"pair_id": pair_id, "error": str(result)},
            )
            processed_results.append(
                {"pair_id": pair_id, "status": "failed", "error": str(result)}
            )
        else:
            session.emit_event(
                EventType.SUBAGENT_RESULT,
                {"pair_id": pair_id, "result": result},
            )
            processed_results.append(
                {"pair_id": pair_id, "status": "completed", "result": result}
            )

    # 4. Session 协调合并
    merged = await merge_from_session(session, agents)

    # 5. 记录会话结束
    session.emit_event(
        EventType.SESSION_END,
        {"reason": "completed", "pairs_count": len(pair_ids)},
    )

    return CoordinationResult(
        task=task,
        agent_results=processed_results,
        merged_result=merged,
        session_events=session.get_events(),
    )