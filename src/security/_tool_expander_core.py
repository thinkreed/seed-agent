"""
渐进式工具扩展器核心模块

根据任务类型、用户权限、复杂度等因素动态扩展可用工具集
"""

import logging
from collections.abc import Callable
from typing import Any

from src.security._tool_expander_config import (
    TASK_TYPE_TIER_MAP,
    TOOL_TIER_CONFIGS,
    TIER_ORDER,
    USER_PERMISSION_TIER_LIMITS,
)
from src.security._tool_expander_types import (
    ToolTier,
    create_expansion_event,
)

logger = logging.getLogger(__name__)


class ProgressiveToolExpander:
    """渐进式工具扩展器

    核心功能:
    - 根据上下文动态确定工具层级
    - 工具层级渐进扩展
    - 扩展历史记录
    - 复杂度自适应

    Example:
        expander = ProgressiveToolExpander()
        tools = expander.get_available_tools({
            "task_type": "implementation",
            "user_permission": "normal",
            "iteration": 5
        })
    """

    def __init__(
        self,
        initial_tier: ToolTier = ToolTier.TIER_0_MINIMAL,
        max_history_size: int = 100,
        enable_auto_expansion: bool = True,
    ):
        """初始化工具扩展器

        Args:
            initial_tier: 初始工具层级
            max_history_size: 扩展历史最大记录数
            enable_auto_expansion: 是否启用自动扩展
        """
        self._current_tier = initial_tier
        self._max_history_size = max_history_size
        self._enable_auto_expansion = enable_auto_expansion
        self._expansion_history: list[Any] = []
        self._registered_tools: set[str] = set()
        self._tool_register_callback: Callable[[str], None] | None = None

        logger.info(
            f"ProgressiveToolExpander initialized: "
            f"initial_tier={initial_tier.value}, "
            f"auto_expansion={enable_auto_expansion}"
        )

    def get_available_tools(self, context: dict[str, Any] | None = None) -> set[str]:
        """获取当前可用工具集

        Args:
            context: 包含 task_type, user_permission, complexity, iteration 等

        Returns:
            可用工具名称集合
        """
        context = context or {}

        if self._enable_auto_expansion:
            # 检查是否需要扩展
            new_tier = self._determine_tier(context)

            if new_tier != self._current_tier:
                self._expand_to_tier(new_tier, context)

        return TOOL_TIER_CONFIGS[self._current_tier].tools

    def get_current_tier(self) -> ToolTier:
        """获取当前工具层级"""
        return self._current_tier

    def get_tier_description(self) -> str:
        """获取当前层级描述"""
        return TOOL_TIER_CONFIGS[self._current_tier].description

    def _determine_tier(self, context: dict[str, Any]) -> ToolTier:
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

        # 3. 复杂度（高复杂度可提升层级）
        complexity = context.get("complexity", 0.0)
        if complexity > 0.8 and user_permission in ("admin", "trusted"):
            complexity_tier = ToolTier.TIER_3_FULL
        elif complexity > 0.5:
            complexity_tier = ToolTier.TIER_2_EXTENDED
        else:
            complexity_tier = ToolTier.TIER_1_BASIC

        # 4. 迭代次数（渐进扩展）
        iteration = context.get("iteration", 0)
        if iteration > 10 and user_permission in ("admin", "trusted"):
            iteration_tier = ToolTier.TIER_3_FULL
        elif iteration > 5:
            iteration_tier = ToolTier.TIER_2_EXTENDED
        elif iteration > 0:
            iteration_tier = ToolTier.TIER_1_BASIC
        else:
            iteration_tier = ToolTier.TIER_0_MINIMAL

        # 5. 综合决策：取所有因素中的最高层级，但不超过权限上限
        candidate_tiers = [task_tier, complexity_tier, iteration_tier]
        highest_candidate = max(candidate_tiers, key=TIER_ORDER.index)

        # 不超过权限上限
        return min(highest_candidate, max_tier, key=TIER_ORDER.index)

    def _expand_to_tier(self, new_tier: ToolTier, context: dict[str, Any]) -> None:
        """扩展到新层级

        Args:
            new_tier: 目标层级
            context: 扩展上下文
        """
        old_tier = self._current_tier

        # 获取新工具集
        old_tools = TOOL_TIER_CONFIGS[old_tier].tools
        new_tools = TOOL_TIER_CONFIGS[new_tier].tools

        # 计算新增工具
        added_tools = new_tools - old_tools

        if not added_tools:
            # 无新工具，只更新层级
            self._current_tier = new_tier
            return

        # 确定扩展原因
        reason = self._determine_expansion_reason(context, old_tier, new_tier)

        # 更新当前层级
        self._current_tier = new_tier

        # 记录扩展历史
        event = create_expansion_event(old_tier, new_tier, added_tools, context, reason)
        self._expansion_history.append(event)

        # 限制历史大小
        if len(self._expansion_history) > self._max_history_size:
            self._expansion_history = self._expansion_history[-self._max_history_size :]

        logger.info(
            f"Tool tier expanded: {old_tier.value} → {new_tier.value}, "
            f"added {len(added_tools)} tools: {sorted(added_tools)}"
        )

    def _determine_expansion_reason(
        self,
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

    def force_expand_to_tier(
        self, target_tier: ToolTier, reason: str = "manual"
    ) -> set[str]:
        """强制扩展到指定层级

        Args:
            target_tier: 目标层级
            reason: 扩展原因

        Returns:
            新增的工具集
        """
        old_tools = TOOL_TIER_CONFIGS[self._current_tier].tools
        new_tools = TOOL_TIER_CONFIGS[target_tier].tools
        added_tools = new_tools - old_tools

        if added_tools:
            event = create_expansion_event(
                self._current_tier,
                target_tier,
                added_tools,
                {"forced": True},
                reason,
            )
            self._expansion_history.append(event)

            logger.info(
                f"Forced tool tier expansion: {self._current_tier.value} → {target_tier.value}, "
                f"reason={reason}"
            )

        self._current_tier = target_tier
        return added_tools

    def reset_to_initial(
        self, initial_tier: ToolTier = ToolTier.TIER_0_MINIMAL
    ) -> None:
        """重置到初始层级"""
        self._current_tier = initial_tier
        logger.info(f"Tool tier reset to: {initial_tier.value}")

    def is_tool_available(self, tool_name: str) -> bool:
        """检查工具是否可用"""
        return tool_name in TOOL_TIER_CONFIGS[self._current_tier].tools

    def get_tool_tier(self, tool_name: str) -> ToolTier | None:
        """获取工具所属的最低层级"""
        for tier in TIER_ORDER:
            if tool_name in TOOL_TIER_CONFIGS[tier].tools:
                return tier
        return None

    def get_expansion_history(self, limit: int = 10) -> list[Any]:
        """获取扩展历史"""
        return self._expansion_history[-limit:]

    def get_expansion_stats(self) -> dict[str, Any]:
        """获取扩展统计"""
        stats: dict[str, Any] = {
            "current_tier": self._current_tier.value,
            "tier_description": TOOL_TIER_CONFIGS[self._current_tier].description,
            "available_tools_count": len(TOOL_TIER_CONFIGS[self._current_tier].tools),
            "total_expansions": len(self._expansion_history),
            "expansion_events": [],
        }

        # 扩展事件摘要
        for event in self._expansion_history[-5:]:
            stats["expansion_events"].append(
                {
                    "timestamp": event.timestamp,
                    "from": event.from_tier.value,
                    "to": event.to_tier.value,
                    "added_count": len(event.added_tools),
                    "reason": event.reason,
                }
            )

        return stats

    def register_tool_callback(self, callback: Callable[[str], None]) -> None:
        """注册工具扩展回调函数

        当工具层级扩展时，回调函数会被调用以注册新工具

        Args:
            callback: 回调函数，接收 (tool_name) 参数
        """
        self._tool_register_callback = callback

    def set_auto_expansion(self, enabled: bool) -> None:
        """设置自动扩展开关"""
        self._enable_auto_expansion = enabled
        logger.info(f"Auto expansion set to: {enabled}")