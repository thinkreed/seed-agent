"""结果合并模块

负责合并多个智能体的执行结果
"""

import json
import logging
from typing import Any

from src.collaboration._types import AgentInstance
from src.session_event_stream import EventType

logger = logging.getLogger(__name__)


async def merge_from_session(
    session: Any,
    agents: list[AgentInstance],
) -> dict[str, Any]:
    """从 Session 合并所有结果

    Args:
        session: SessionEventStream 实例
        agents: 智能体列表

    Returns:
        合并结果字典
    """
    # 获取所有 subagent_result 事件
    pair_events = [
        e
        for e in session.get_events()
        if e["type"] == EventType.SUBAGENT_RESULT.value
    ]

    # 合并逻辑
    successful_pairs = [e for e in pair_events if "error" not in e["data"]]
    failed_pairs = [e for e in pair_events if "error" in e["data"]]

    # 收集结果
    all_results: list[dict[str, Any]] = []
    for event in successful_pairs:
        result_data = event["data"].get("result", {})
        if isinstance(result_data, dict):
            all_results.append(result_data)

    # 生成合并摘要
    merged_summary = await generate_merge_summary(all_results, agents)

    return {
        "total_pairs": len(pair_events),
        "successful_pairs": len(successful_pairs),
        "failed_pairs": len(failed_pairs),
        "results": all_results,
        "merged_summary": merged_summary,
    }


async def generate_merge_summary(
    results: list[dict[str, Any]],
    agents: list[AgentInstance],
) -> str:
    """生成合并摘要

    Args:
        results: 结果列表
        agents: 智能体列表

    Returns:
        合并摘要字符串
    """
    if not results:
        return "No results to merge"

    if not agents:
        return f"Collected {len(results)} results"

    # 使用第一个大脑生成摘要
    prompt = f"""请总结以下多个智能体的执行结果:

{json.dumps(results[:5], ensure_ascii=False, indent=2)}

请输出:
1. 各智能体贡献总结
2. 整体完成情况
3. 遗留问题或下一步建议
"""

    try:
        response = await agents[0].llm_client.reason(
            [{"role": "user", "content": prompt}]
        )
        return (
            response.get("choices", [{}])[0].get("message", {}).get("content", "")
        )

    except Exception as e:
        logger.exception(f"Merge summary failed: {e}")
        return f"Generated {len(results)} results"