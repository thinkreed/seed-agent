"""渐进式工具扩展器核心模块"""

import logging
from collections.abc import Callable
from typing import Any

from src.security._tool_expander_config import TOOL_TIER_CONFIGS, TIER_ORDER
from src.security._tool_expander_determine import determine_expansion_reason, determine_tier
from src.security._tool_expander_types import ToolTier, create_expansion_event

logger = logging.getLogger(__name__)


class ProgressiveToolExpander:
    """渐进式工具扩展器"""

    def __init__(self, initial_tier: ToolTier = ToolTier.TIER_0_MINIMAL, max_history_size: int = 100, enable_auto_expansion: bool = True):
        self._current_tier = initial_tier
        self._max_history_size = max_history_size
        self._enable_auto_expansion = enable_auto_expansion
        self._expansion_history: list[Any] = []
        self._registered_tools: set[str] = set()
        self._tool_register_callback: Callable[[str], None] | None = None
        logger.info(f"ProgressiveToolExpander initialized: initial_tier={initial_tier.value}")

    def get_available_tools(self, context: dict[str, Any] | None = None) -> set[str]:
        """获取当前可用工具集"""
        context = context or {}
        if self._enable_auto_expansion:
            new_tier = determine_tier(context)
            if new_tier != self._current_tier:
                self._expand_to_tier(new_tier, context)
        return TOOL_TIER_CONFIGS[self._current_tier].tools

    def get_current_tier(self) -> ToolTier:
        return self._current_tier

    def get_tier_description(self) -> str:
        return TOOL_TIER_CONFIGS[self._current_tier].description

    def _expand_to_tier(self, new_tier: ToolTier, context: dict[str, Any]) -> None:
        old_tier = self._current_tier
        added_tools = TOOL_TIER_CONFIGS[new_tier].tools - TOOL_TIER_CONFIGS[old_tier].tools
        if not added_tools:
            self._current_tier = new_tier
            return
        reason = determine_expansion_reason(context, old_tier, new_tier)
        self._current_tier = new_tier
        event = create_expansion_event(old_tier, new_tier, added_tools, context, reason)
        self._expansion_history.append(event)
        if len(self._expansion_history) > self._max_history_size:
            self._expansion_history = self._expansion_history[-self._max_history_size:]
        logger.info(f"Tool tier expanded: {old_tier.value} -> {new_tier.value}, added {len(added_tools)} tools")

    def force_expand_to_tier(self, target_tier: ToolTier, reason: str = "manual") -> set[str]:
        added_tools = TOOL_TIER_CONFIGS[target_tier].tools - TOOL_TIER_CONFIGS[self._current_tier].tools
        if added_tools:
            event = create_expansion_event(self._current_tier, target_tier, added_tools, {"forced": True}, reason)
            self._expansion_history.append(event)
            logger.info(f"Forced tool tier expansion: reason={reason}")
        self._current_tier = target_tier
        return added_tools

    def reset_to_initial(self, initial_tier: ToolTier = ToolTier.TIER_0_MINIMAL) -> None:
        self._current_tier = initial_tier
        logger.info(f"Tool tier reset to: {initial_tier.value}")

    def is_tool_available(self, tool_name: str) -> bool:
        return tool_name in TOOL_TIER_CONFIGS[self._current_tier].tools

    def get_tool_tier(self, tool_name: str) -> ToolTier | None:
        for tier in TIER_ORDER:
            if tool_name in TOOL_TIER_CONFIGS[tier].tools:
                return tier
        return None

    def get_expansion_history(self, limit: int = 10) -> list[Any]:
        return self._expansion_history[-limit:]

    def get_expansion_stats(self) -> dict[str, Any]:
        stats = {
            "current_tier": self._current_tier.value,
            "tier_description": TOOL_TIER_CONFIGS[self._current_tier].description,
            "available_tools_count": len(TOOL_TIER_CONFIGS[self._current_tier].tools),
            "total_expansions": len(self._expansion_history),
            "expansion_events": [],
        }
        for event in self._expansion_history[-5:]:
            stats["expansion_events"].append({
                "timestamp": event.timestamp, "from": event.from_tier.value,
                "to": event.to_tier.value, "added_count": len(event.added_tools), "reason": event.reason,
            })
        return stats

    def register_tool_callback(self, callback: Callable[[str], None]) -> None:
        self._tool_register_callback = callback

    def set_auto_expansion(self, enabled: bool) -> None:
        self._enable_auto_expansion = enabled
        logger.info(f"Auto expansion set to: {enabled}")