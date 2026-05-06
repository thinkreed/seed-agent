"""
上下文管理函数

提供关键信息提取和上下文重置功能。
"""

import logging

logger = logging.getLogger("seed_agent.ralph")


def extract_critical_context(history: list[dict]) -> str | None:
    """
    从历史记录中提取关键上下文

    Args:
        history: 对话历史列表

    Returns:
        关键上下文摘要，或 None
    """
    if not history:
        return None

    # 提取最后一条 assistant 消息的摘要
    for msg in reversed(history):
        if msg.get("role") == "assistant" and msg.get("content"):
            return f"上次执行摘要: {msg['content'][:300]}"

    return None


def reset_context(
    history: list[dict],
    iteration: int,
    reset_interval: int,
    preserved_context: str | None = None,
) -> bool:
    """
    条件性重置上下文（防止漂移）

    Args:
        history: 对话历史列表（会被清空）
        iteration: 当前迭代次数
        reset_interval: 重置间隔
        preserved_context: 保留的关键上下文

    Returns:
        True 表示执行了重置
    """
    # 仅在指定间隔执行
    if iteration % reset_interval != 0:
        return False

    # 清空历史
    history.clear()

    # 重新注入保留信息（如有）
    if preserved_context:
        history.append(
            {
                "role": "system",
                "content": f"[迭代 {iteration} 状态摘要]\n{preserved_context}",
            }
        )

    logger.info(f"Context reset at iteration {iteration}")
    return True