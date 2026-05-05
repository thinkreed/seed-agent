"""生命周期钩子注销模块

包含 unregister 和 clear_hooks 方法。
"""

import logging
from collections.abc import Callable
from typing import Any

from src.lifecycle_hooks._types import HookPoint

logger = logging.getLogger(__name__)


class UnregisterMixin:
    """注销方法 mixin

    提供 unregister, clear_hooks 方法。
    需要 _hooks 和 _hook_stats 属性。
    """

    _hooks: dict[str, list[tuple[int, Callable, str]]]
    _hook_stats: dict[str, Any]

    def unregister(self, hook_id: str) -> bool:
        """注销钩子

        Args:
            hook_id: 钩子唯一标识

        Returns:
            是否成功注销
        """
        for hooks in self._hooks.values():
            for i, (_, _, id_) in enumerate(hooks):
                if id_ == hook_id:
                    hooks.pop(i)
                    if hook_id in self._hook_stats:
                        del self._hook_stats[hook_id]
                    logger.info(f"Hook unregistered: {hook_id}")
                    return True
        return False

    def clear_hooks(self, hook_point: HookPoint | str | None = None) -> int:
        """清除钩子

        Args:
            hook_point: 指定清除的钩子节点，None 表示清除所有

        Returns:
            清除的钩子数量
        """
        count = 0
        if hook_point:
            point_value = (
                hook_point.value if isinstance(hook_point, HookPoint) else hook_point
            )
            if point_value in self._hooks:
                for _, _, hook_id in self._hooks[point_value]:
                    if hook_id in self._hook_stats:
                        del self._hook_stats[hook_id]
                    count += 1
                self._hooks[point_value] = []
        else:
            for point in self._hooks:
                for _, _, hook_id in self._hooks[point]:
                    if hook_id in self._hook_stats:
                        del self._hook_stats[hook_id]
                    count += 1
                self._hooks[point] = []

        logger.info(f"Cleared {count} hooks")
        return count


__all__ = ["UnregisterMixin"]