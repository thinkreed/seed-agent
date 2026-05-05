"""
渐进式工具扩展器层级决策模块

包含层级确定逻辑
"""

from typing import Any

from src.security._tool_expander_config import (
    TASK_TYPE_TIER_MAP,
    TIER_ORDER,
    USER_PERMISSION_TIER_LIMITS,
)
from src.security._tool_expander_types import ToolTier


def determine_tier(context: dict[str, Any]) -> ToolTier:
    """确定当前应使用的工具层级

    决策因素:
    1. 用户权限等级（上限）
    2. 任务类型（推荐层级）
    3. 任务复杂度（0.0-1.0）
    4. 迭代次数（渐进扩展）
    """
    # 1. 用户权限上限
    user_permission = context.get("user_permission", "normal")
    max_tier = USER_PERMISSION_TIER_LIMITS.get(
        user_permission, ToolTier.TIER_2_EXTENDED
    )

    # 2. 任务类型
    task_type = context.get("task_type", "")
    task_tier = TASK_TYPE_TIER_MAP.get(task_type, ToolTier.TIER_1_BASIC)

    # 3. 复杂度
    complexity = context.get("complexity", 0.0)
    if complexity > 0.8 and user_permission in ("admin", "trusted"):
        complexity_tier = ToolTier.TIER_3_FULL
    elif complexity > 0.5:
        complexity_tier = ToolTier.TIER_2_EXTENDED
    else:
        complexity_tier = ToolTier.TIER_1_BASIC

    # 4. 迭代次数
    iteration = context.get("iteration", 0)
    if iteration > 10 and user_permission in ("admin", "trusted"):
        iteration_tier = ToolTier.TIER_3_FULL
    elif iteration > 5:
        iteration_tier = ToolTier.TIER_2_EXTENDED
    elif iteration > 0:
        iteration_tier = ToolTier.TIER_1_BASIC
    else:
        iteration_tier = ToolTier.TIER_0_MINIMAL

    # 5. 综合决策
    candidate_tiers = [task_tier, complexity_tier, iteration_tier]
    highest_candidate = max(candidate_tiers, key=TIER_ORDER.index)

    return min(highest_candidate, max_tier, key=TIER_ORDER.index)


def determine_expansion_reason(
    context: dict[str, Any],
    old_tier: ToolTier,
    new_tier: ToolTier,
) -> str:
    """确定扩展原因"""
    reasons = []

    if context.get("task_type"):
        reasons.append(f"task_type={context['task_type']}")

    if context.get("complexity", 0) > 0.5:
        reasons.append(f"complexity={context['complexity']:.2f}")

    if context.get("iteration", 0) > 0:
        reasons.append(f"iteration={context['iteration']}")

    if context.get("user_permission"):
        reasons.append(f"user_permission={context['user_permission']}")

    if not reasons:
        reasons.append("automatic")

    return ", ".join(reasons)