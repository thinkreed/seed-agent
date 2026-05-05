"""
渐进式工具扩展器类型定义

包含枚举、数据类和事件定义
"""

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ToolTier(StrEnum):
    """工具层级"""

    TIER_0_MINIMAL = "tier_0_minimal"
    TIER_1_BASIC = "tier_1_basic"
    TIER_2_EXTENDED = "tier_2_extended"
    TIER_3_FULL = "tier_3_full"


@dataclass
class ToolTierConfig:
    """工具层级配置"""

    description: str
    tools: set[str]
    trigger_conditions: list[str]


@dataclass
class ExpansionEvent:
    """工具扩展事件"""

    timestamp: float
    from_tier: ToolTier
    to_tier: ToolTier
    added_tools: set[str]
    context: dict[str, Any]
    reason: str


def create_expansion_event(
    from_tier: ToolTier,
    to_tier: ToolTier,
    added_tools: set[str],
    context: dict[str, Any],
    reason: str,
) -> ExpansionEvent:
    """创建扩展事件的工厂函数

    Args:
        from_tier: 原层级
        to_tier: 目标层级
        added_tools: 新增工具集
        context: 扩展上下文
        reason: 扩展原因

    Returns:
        ExpansionEvent: 扩展事件实例
    """
    return ExpansionEvent(
        timestamp=time.time(),
        from_tier=from_tier,
        to_tier=to_tier,
        added_tools=added_tools,
        context=context,
        reason=reason,
    )