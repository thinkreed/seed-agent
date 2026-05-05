"""生命周期钩子装饰器模块

包含 register 装饰器模式和主注册方法。
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any, overload

from src.lifecycle_hooks._types import HookPoint

logger = logging.getLogger(__name__)


class DecoratorMixin:
    """装饰器注册方法 mixin

    提供 register 方法（支持装饰器模式）。
    需要 _hooks 和 _hook_stats 属性。
    """

    _hooks: dict[str, list[tuple[int, Callable, str]]]
    _hook_stats: dict[str, Any]

    @overload
    def register(
        self,
        hook_point: HookPoint | str,
        callback: None = None,
        priority: int = 0,
        name: str | None = None,
        description: str | None = None,
    ) -> Callable[[Callable], Callable]: ...

    @overload
    def register(
        self,
        hook_point: HookPoint | str,
        callback: Callable,
        priority: int = 0,
        name: str | None = None,
        description: str | None = None,
    ) -> str: ...

    def register(
        self,
        hook_point: HookPoint | str,
        callback: Callable | None = None,
        priority: int = 0,
        name: str | None = None,
        description: str | None = None,
    ) -> str | Callable:
        """注册钩子

        Args:
            hook_point: 钩子节点名称
            callback: 钩子回调函数，可为 None 用于装饰器模式
            priority: 执行优先级 (数值越小越先执行)
            name: 钩子名称
            description: 钩子描述

        Returns:
            hook_id 或 Callable: 装饰器返回函数
        """
        point_value = (
            hook_point.value if isinstance(hook_point, HookPoint) else hook_point
        )

        if point_value not in self._hooks:
            raise ValueError(f"Unknown hook point: {point_value}")

        if callback is None:

            def decorator(func: Callable) -> Callable:
                self._do_register(point_value, func, priority, name, description)
                return func

            return decorator

        return self._do_register(point_value, callback, priority, name, description)

    def _do_register(
        self,
        point_value: str,
        callback: Callable,
        priority: int,
        name: str | None,
        description: str | None,
    ) -> str:
        """实际注册钩子"""
        from src.lifecycle_hooks._types import HookStats

        hook_id = name or f"{point_value}_{len(self._hooks[point_value])}"

        for _, _, existing_id in self._hooks[point_value]:
            if existing_id == hook_id:
                logger.warning(f"Hook {hook_id} already exists, replacing")
                self.unregister(hook_id)
                break

        self._hooks[point_value].append((priority, callback, hook_id))
        self._hooks[point_value].sort(key=lambda x: x[0])

        self._hook_stats[hook_id] = HookStats(
            hook_id=hook_id,
            hook_point=point_value,
            priority=priority,
        )

        logger.info(
            f"Hook registered: {hook_id} at {point_value} "
            f"(priority={priority}, async={asyncio.iscoroutinefunction(callback)})"
        )
        return hook_id


__all__ = ["DecoratorMixin"]