"""生命周期钩子注册方法模块

包含钩子注册、注销和清除相关方法：
- register (支持装饰器模式)
- _do_register
- unregister
- clear_hooks
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any, overload

from src.lifecycle_hooks._types import HookPoint

logger = logging.getLogger(__name__)


class RegistrationMixin:
    """钩子注册方法 mixin

    提供 register, unregister, clear_hooks 方法。
    需要 _hooks 和 _hook_stats 属性。
    """

    # 类型提示（实际由 LifecycleHookRegistry 提供）
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
            callback: 钩子回调函数 (接受 context 参数)，可为 None 用于装饰器模式
            priority: 执行优先级 (数值越小越先执行)
            name: 钩子名称 (用于标识)
            description: 钩子描述

        Returns:
            hook_id: 钩子唯一标识
            或 Callable: 当作为装饰器使用时返回装饰后的函数

        Raises:
            ValueError: 未知的钩子节点
        """
        # 转换为字符串值
        point_value = (
            hook_point.value if isinstance(hook_point, HookPoint) else hook_point
        )

        if point_value not in self._hooks:
            raise ValueError(f"Unknown hook point: {point_value}")

        # 装饰器模式支持
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

        # 生成 hook_id
        hook_id = name or f"{point_value}_{len(self._hooks[point_value])}"

        # 检查是否已存在
        for _, _, existing_id in self._hooks[point_value]:
            if existing_id == hook_id:
                logger.warning(f"Hook {hook_id} already exists, replacing")
                self.unregister(hook_id)
                break

        # 添加并按优先级排序
        self._hooks[point_value].append((priority, callback, hook_id))
        self._hooks[point_value].sort(key=lambda x: x[0])

        # 初始化统计
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


__all__ = ["RegistrationMixin"]