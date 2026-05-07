"""生命周期钩子查询方法模块

包含钩子查询和统计相关方法：
- list_hooks
- get_hook_stats
- get_all_stats
- get_hook_count
- has_hook
- get_hook_points
- get_hook_point_description
"""

import logging
from collections.abc import Callable
from typing import Any

from src.lifecycle_hooks._types import HOOK_POINT_DESCRIPTIONS, HookPoint

logger = logging.getLogger(__name__)


class QueryMixin:
    """钩子查询方法 mixin

    提供 list_hooks, get_hook_stats, get_all_stats 等方法。
    需要 _hooks 和 _hook_stats 属性。
    """

    # 类型提示（实际由 LifecycleHookRegistry 提供）
    _hooks: dict[str, list[tuple[int, Callable, str]]]
    _hook_stats: dict[str, Any]
    _global_stats: dict[str, Any]

    def list_hooks(
        self, hook_point: HookPoint | str | None = None
    ) -> list[dict[str, Any]]:
        """列出已注册钩子

        Args:
            hook_point: 指定查询的钩子节点，None 表示查询所有

        Returns:
            钩子列表
        """
        if hook_point:
            point_value = (
                hook_point.value if isinstance(hook_point, HookPoint) else hook_point
            )
            return [
                {
                    "hook_id": id_,
                    "priority": pri,
                    "hook_point": point_value,
                    "callback": str(cb),
                }
                for pri, cb, id_ in self._hooks.get(point_value, [])
            ]

        return [
            {
                "hook_point": point,
                "hook_id": id_,
                "priority": pri,
                "callback": str(cb),
            }
            for point, hooks in self._hooks.items()
            for pri, cb, id_ in hooks
        ]

    def get_hook_stats(self, hook_id: str) -> dict[str, Any] | None:
        """获取钩子执行统计

        Args:
            hook_id: 钩子唯一标识

        Returns:
            统计数据
        """
        stats = self._hook_stats.get(hook_id)
        return stats.to_dict() if stats else None

    def get_all_stats(self) -> dict[str, Any]:
        """获取所有统计

        Returns:
            全局统计和各钩子统计
        """
        return {
            "global": self._global_stats,
            "hooks": {
                hook_id: stats.to_dict() for hook_id, stats in self._hook_stats.items()
            },
        }

    def get_hook_count(self, hook_point: HookPoint | str | None = None) -> int:
        """获取钩子数量

        Args:
            hook_point: 指定查询的钩子节点

        Returns:
            钩子数量
        """
        if hook_point:
            point_value = (
                hook_point.value if isinstance(hook_point, HookPoint) else hook_point
            )
            return len(self._hooks.get(point_value, []))

        return sum(len(hooks) for hooks in self._hooks.values())

    def has_hook(self, hook_id: str) -> bool:
        """检查钩子是否存在

        Args:
            hook_id: 钩子唯一标识

        Returns:
            是否存在
        """
        return hook_id in self._hook_stats

    def get_hook_points(self) -> list[str]:
        """获取所有钩子节点"""
        return list(self._hooks.keys())

    def get_hook_point_description(self, hook_point: str) -> str:
        """获取钩子节点描述"""
        return HOOK_POINT_DESCRIPTIONS.get(hook_point, "未知节点")


__all__ = ["QueryMixin"]