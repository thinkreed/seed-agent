"""
Hook 结果聚合器

合并多个钩子的执行结果：
- deny 优先：任何 deny 都导致最终 deny
- ask 汇总：收集所有 ask 的原因
- allow 统计：记录允许的钩子数量
"""

import logging
from typing import Any

from src.tools import PermissionDecision

logger = logging.getLogger(__name__)


class HookAggregator:
    """钩子结果聚合器

    合并多个钩子的执行结果：
    - deny 优先：任何 deny 都导致最终 deny
    - ask 汇总：收集所有 ask 的原因
    - allow 统计：记录允许的钩子数量
    """

    @staticmethod
    def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
        """聚合多个钩子结果

        Args:
            results: 钩子执行结果列表

        Returns:
            聚合后的最终决策
        """
        if not results:
            return {"decision": PermissionDecision.Allow.value, "reasons": []}

        # deny 优先
        deny_reasons = [
            r.get("reason", "Security violation")
            for r in results
            if r.get("decision") == PermissionDecision.Deny.value
        ]
        if deny_reasons:
            return {
                "decision": PermissionDecision.Deny.value,
                "reasons": deny_reasons,
                "message": f"Denied by hooks: {deny_reasons[0]}",
            }

        # ask 汇总
        ask_reasons = [
            r.get("reason", "Needs confirmation")
            for r in results
            if r.get("decision") == PermissionDecision.Ask.value
        ]
        if ask_reasons:
            return {
                "decision": PermissionDecision.Ask.value,
                "reasons": ask_reasons,
                "message": f"Confirmation required: {', '.join(ask_reasons)}",
            }

        # 全部 allow
        return {
            "decision": PermissionDecision.Allow.value,
            "reasons": [],
            "allowed_count": len(results),
        }


__all__ = ["HookAggregator"]