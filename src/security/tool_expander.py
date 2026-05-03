"""
渐进式工具扩展器 - ProgressiveToolExpander

根据任务类型、用户权限、复杂度等因素动态扩展可用工具集

工具层级:
- Tier 0 Minimal: 最小工具集，只读操作
- Tier 1 Basic: 基础工具集，常用操作
- Tier 2 Extended: 扩展工具集，写入操作
- Tier 3 Full: 完整工具集，高风险操作

参考来源: Harness Engineering "渐进式工具扩展"
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ToolTier(str, Enum):
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


# 工具层级定义
TOOL_TIER_CONFIGS: dict[ToolTier, ToolTierConfig] = {
    ToolTier.TIER_0_MINIMAL: ToolTierConfig(
        description="最小工具集 - 只读操作",
        tools={
            "file_read",
            "list_directory",
            "ask_user",
            "search_history",
            "read_memory_index",
            "search_memory",
            "load_skill",
            "git_status",
            "git_diff",
            "list_subagents",
            "check_ralph_status",
            "list_scheduled_tasks",
        },
        trigger_conditions=["session_start", "initial_context"],
    ),
    ToolTier.TIER_1_BASIC: ToolTierConfig(
        description="基础工具集 - 常用操作",
        tools={
            # Tier 0 工具
            "file_read",
            "list_directory",
            "ask_user",
            "search_history",
            "read_memory_index",
            "search_memory",
            "load_skill",
            "git_status",
            "git_diff",
            "list_subagents",
            "check_ralph_status",
            "list_scheduled_tasks",
            # 新增工具
            "find_file",
            "grep_search",
            "run_diagnosis",
            "wait_for_subagent",
            "aggregate_subagent_results",
        },
        trigger_conditions=["first_user_request", "exploration_task"],
    ),
    ToolTier.TIER_2_EXTENDED: ToolTierConfig(
        description="扩展工具集 - 写入操作",
        tools={
            # Tier 1 工具（继承）
            "file_read",
            "list_directory",
            "ask_user",
            "search_history",
            "read_memory_index",
            "search_memory",
            "load_skill",
            "git_status",
            "git_diff",
            "list_subagents",
            "check_ralph_status",
            "list_scheduled_tasks",
            "find_file",
            "grep_search",
            "run_diagnosis",
            "wait_for_subagent",
            "aggregate_subagent_results",
            # 新增写入工具
            "file_write",
            "file_edit",
            "create_directory",
            "write_memory",
            "git_commit",
            "spawn_subagent",
            "create_scheduled_task",
            "run_test",
            "run_python_script",
        },
        trigger_conditions=["implementation_task", "refactoring_task", "iteration_threshold"],
    ),
    ToolTier.TIER_3_FULL: ToolTierConfig(
        description="完整工具集 - 高风险操作",
        tools={
            # Tier 2 工具（继承）
            "file_read",
            "list_directory",
            "ask_user",
            "search_history",
            "read_memory_index",
            "search_memory",
            "load_skill",
            "git_status",
            "git_diff",
            "list_subagents",
            "check_ralph_status",
            "list_scheduled_tasks",
            "find_file",
            "grep_search",
            "run_diagnosis",
            "wait_for_subagent",
            "aggregate_subagent_results",
            "file_write",
            "file_edit",
            "create_directory",
            "write_memory",
            "git_commit",
            "spawn_subagent",
            "create_scheduled_task",
            "run_test",
            "run_python_script",
            # 新增高风险工具
            "code_as_policy",
            "run_shell_command",
            "delete_file",
            "install_package",
            "git_push",
            "kill_subagent",
            "remove_scheduled_task",
            "mark_ralph_complete",
            "start_ralph_loop",
        },
        trigger_conditions=["trusted_user", "complex_task", "admin_request"],
    ),
}


@dataclass
class ExpansionEvent:
    """工具扩展事件"""
    timestamp: float
    from_tier: ToolTier
    to_tier: ToolTier
    added_tools: set[str]
    context: dict[str, Any]
    reason: str


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

    # 任务类型到工具层级映射
    TASK_TYPE_TIER_MAP: dict[str, ToolTier] = {
        "exploration": ToolTier.TIER_1_BASIC,
        "review": ToolTier.TIER_1_BASIC,
        "analysis": ToolTier.TIER_1_BASIC,
        "search": ToolTier.TIER_1_BASIC,
        "implementation": ToolTier.TIER_2_EXTENDED,
        "refactoring": ToolTier.TIER_2_EXTENDED,
        "fix": ToolTier.TIER_2_EXTENDED,
        "debug": ToolTier.TIER_2_EXTENDED,
        "deployment": ToolTier.TIER_3_FULL,
        "system": ToolTier.TIER_3_FULL,
        "admin": ToolTier.TIER_3_FULL,
    }

    # 用户权限到工具层级上限映射
    USER_PERMISSION_TIER_LIMITS: dict[str, ToolTier] = {
        "admin": ToolTier.TIER_3_FULL,
        "trusted": ToolTier.TIER_3_FULL,
        "normal": ToolTier.TIER_2_EXTENDED,
        "guest": ToolTier.TIER_1_BASIC,
        "restricted": ToolTier.TIER_0_MINIMAL,
    }

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
        self._expansion_history: list[ExpansionEvent] = []
        self._registered_tools: set[str] = set()

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
        max_tier = self.USER_PERMISSION_TIER_LIMITS.get(user_permission, ToolTier.TIER_2_EXTENDED)

        # 2. 任务类型
        task_type = context.get("task_type", "")
        task_tier = self.TASK_TYPE_TIER_MAP.get(task_type, ToolTier.TIER_1_BASIC)

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
        tier_order = [
            ToolTier.TIER_0_MINIMAL,
            ToolTier.TIER_1_BASIC,
            ToolTier.TIER_2_EXTENDED,
            ToolTier.TIER_3_FULL,
        ]

        candidate_tiers = [task_tier, complexity_tier, iteration_tier]
        highest_candidate = max(candidate_tiers, key=lambda t: tier_order.index(t))

        # 不超过权限上限
        final_tier = min(highest_candidate, max_tier, key=lambda t: tier_order.index(t))

        return final_tier

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
        event = ExpansionEvent(
            timestamp=time.time(),
            from_tier=old_tier,
            to_tier=new_tier,
            added_tools=added_tools,
            context=context,
            reason=reason,
        )
        self._expansion_history.append(event)

        # 限制历史大小
        if len(self._expansion_history) > self._max_history_size:
            self._expansion_history = self._expansion_history[-self._max_history_size:]

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

    def force_expand_to_tier(self, target_tier: ToolTier, reason: str = "manual") -> set[str]:
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
            event = ExpansionEvent(
                timestamp=time.time(),
                from_tier=self._current_tier,
                to_tier=target_tier,
                added_tools=added_tools,
                context={"forced": True},
                reason=reason,
            )
            self._expansion_history.append(event)

            logger.info(
                f"Forced tool tier expansion: {self._current_tier.value} → {target_tier.value}, "
                f"reason={reason}"
            )

        self._current_tier = target_tier
        return added_tools

    def reset_to_initial(self, initial_tier: ToolTier = ToolTier.TIER_0_MINIMAL) -> None:
        """重置到初始层级"""
        self._current_tier = initial_tier
        logger.info(f"Tool tier reset to: {initial_tier.value}")

    def is_tool_available(self, tool_name: str) -> bool:
        """检查工具是否可用"""
        return tool_name in TOOL_TIER_CONFIGS[self._current_tier].tools

    def get_tool_tier(self, tool_name: str) -> ToolTier | None:
        """获取工具所属的最低层级"""
        for tier in [
            ToolTier.TIER_0_MINIMAL,
            ToolTier.TIER_1_BASIC,
            ToolTier.TIER_2_EXTENDED,
            ToolTier.TIER_3_FULL,
        ]:
            if tool_name in TOOL_TIER_CONFIGS[tier].tools:
                return tier
        return None

    def get_expansion_history(self, limit: int = 10) -> list[ExpansionEvent]:
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
            stats["expansion_events"].append({
                "timestamp": event.timestamp,
                "from": event.from_tier.value,
                "to": event.to_tier.value,
                "added_count": len(event.added_tools),
                "reason": event.reason,
            })

        return stats

    def register_tool_callback(self, callback: callable) -> None:
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