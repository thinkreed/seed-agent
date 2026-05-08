"""预算相关防御模块

提供预算管理功能:
- Layer 1: 预算警告注入（70%/90%阈值）
- Layer 4: 递减重试预算（失败重试递减）

从 _defense.py 拆分，支持 DefenseState 调用。
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

logger = logging.getLogger("seed_agent")


# === Layer 4: 递减重试预算 ===


def get_retry_budget(
    retry_count: int,
    max_iterations_per_task: int,
    retry_decay_factors: list[float],
) -> int:
    """计算当前重试的迭代预算

    Args:
        retry_count: 当前重试次数
        max_iterations_per_task: 基础迭代上限
        retry_decay_factors: 递减因子列表

    Returns:
        当前重试轮次的迭代上限
        - 第1次重试: 100% 基础预算
        - 第2次重试: 50% 基础预算
        - 第3次重试: 25% 基础预算
        - 超过上限: 0（不再执行）
    """
    if retry_count >= len(retry_decay_factors):
        logger.warning(
            f"Retry count {retry_count} exceeds max "
            f"{len(retry_decay_factors)}, returning 0 budget"
        )
        return 0

    decay_factor = retry_decay_factors[retry_count]
    budget = int(max_iterations_per_task * decay_factor)
    logger.info(
        f"Retry budget: base={max_iterations_per_task}, retry={retry_count}, "
        f"factor={decay_factor}, budget={budget}"
    )
    return budget


# === Layer 1: 预算警告注入 ===


async def inject_budget_warning(
    current: int,
    max_budget: int,
    agent: "AgentLoop",
    budget_warning_threshold: float,
    budget_urgent_threshold: float,
    budget_warning_sent: bool,
    budget_urgent_sent: bool,
) -> tuple[bool, bool]:
    """注入预算警告消息

    在剩余预算达到阈值时，注入警告消息到 Agent 对话历史，
    让 Agent 能够感知剩余预算并主动规划收尾。

    Args:
        current: 当前已使用的迭代次数
        max_budget: 最大迭代次数预算
        agent: AgentLoop 实例（用于注入消息）
        budget_warning_threshold: 警告阈值（如 0.7 表示 70%）
        budget_urgent_threshold: 紧急阈值（如 0.9 表示 90%）
        budget_warning_sent: 是否已发送警告
        budget_urgent_sent: 是否已发送紧急警告

    Returns:
        (new_budget_warning_sent, new_budget_urgent_sent)
    """
    percentage = current / max_budget * 100

    # 70% 预算警告（仅发送一次）
    if percentage >= budget_warning_threshold * 100 and not budget_warning_sent:
        remaining = max_budget - current
        warning_msg = (
            f"[BUDGET WARNING] 已使用 {current}/{max_budget} 轮迭代 ({percentage:.0f}%)。"
            f"剩余 {remaining} 轮。建议开始总结和收尾工作。"
        )
        agent.inject_system_message(warning_msg)
        logger.info(f"Budget warning injected at {percentage:.0f}%")
        budget_warning_sent = True

    # 90% 紧急警告（仅发送一次）
    if percentage >= budget_urgent_threshold * 100 and not budget_urgent_sent:
        remaining = max_budget - current
        urgent_msg = (
            f"[BUDGET URGENT] 已使用 {current}/{max_budget} 轮 ({percentage:.0f}%)。"
            f"仅剩 {remaining} 轮。请立即执行最终操作。"
        )
        agent.inject_system_message(urgent_msg)
        logger.warning(f"Budget urgent warning injected at {percentage:.0f}%")
        budget_urgent_sent = True

    return budget_warning_sent, budget_urgent_sent