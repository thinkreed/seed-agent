"""
生命周期钩子注册中心

基于 Harness Engineering "确定性生命周期钩子" 设计：
- 在智能体生命周期的关键节点自动触发预设动作
- 由系统确保关键流程被执行，不依赖可能被模型遗忘的指令
- 支持动态注册、优先级管理、执行统计
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, overload

from src.lifecycle_hooks._types import (
    HookExecutionResult,
    HookPoint,
    HookStats,
    HookTriggerReport,
    HOOK_POINT_DESCRIPTIONS,
)

logger = logging.getLogger(__name__)


class LifecycleHookRegistry:
    """确定性生命周期钩子注册中心

    核心设计：
    - 统一注册：所有钩子集中管理
    - 优先级执行：数值越小越先执行
    - 执行统计：调用次数、成功/失败率
    - 失败处理：钩子失败不中断主流程

    使用示例：
        registry = LifecycleHookRegistry()

        # 注册钩子
        registry.register(
            HookPoint.TOOL_CALL_BEFORE,
            my_permission_check,
            priority=0,
            name="permission_check"
        )

        # 触发钩子
        report = await registry.trigger(
            HookPoint.TOOL_CALL_BEFORE,
            {"tool_name": "file_read", "tool_args": {...}}
        )
    """

    def __init__(self) -> None:
        """初始化钩子注册中心"""
        # 钩子存储: {hook_point: [(priority, callback, hook_id), ...]}
        self._hooks: dict[str, list[tuple[int, Callable, str]]] = {
            point.value: [] for point in HookPoint
        }
        # 执行统计: {hook_id: HookStats}
        self._hook_stats: dict[str, HookStats] = {}
        # 全局统计
        self._global_stats: dict[str, Any] = {
            "total_triggers": 0,
            "total_executions": 0,
            "total_failures": 0,
            "total_skips": 0,
        }

        logger.info("LifecycleHookRegistry initialized")

    # === 注册 ===

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

    # === 触发 ===

    async def trigger(
        self,
        hook_point: HookPoint | str,
        context: dict[str, Any],
        fail_fast: bool = False,
    ) -> HookTriggerReport:
        """触发钩子

        Args:
            hook_point: 钩子节点名称
            context: 钩子上下文数据
            fail_fast: 是否在第一个失败时停止

        Returns:
            执行报告
        """
        point_value = (
            hook_point.value if isinstance(hook_point, HookPoint) else hook_point
        )

        if point_value not in self._hooks:
            logger.warning(f"Unknown hook point: {point_value}")
            return HookTriggerReport(
                hook_point=point_value,
                hooks_count=0,
                hooks_executed=0,
                hooks_failed=0,
                hooks_skipped=0,
            )

        hooks = self._hooks[point_value]
        report = HookTriggerReport(
            hook_point=point_value,
            hooks_count=len(hooks),
            hooks_executed=0,
            hooks_failed=0,
            hooks_skipped=0,
        )

        start_time = time.time()

        for _, callback, hook_id in hooks:
            hook_start = time.time()
            stats = self._hook_stats.get(hook_id)

            try:
                # 执行钩子
                if asyncio.iscoroutinefunction(callback):
                    result = await callback(context)
                else:
                    result = callback(context)

                # 更新统计
                if stats:
                    stats.total_calls += 1
                    stats.success_calls += 1
                    stats.last_call_time = time.time()
                    stats.total_duration_ms += (time.time() - hook_start) * 1000

                report.hooks_executed += 1
                report.results.append(
                    HookExecutionResult(
                        hook_id=hook_id,
                        status="success",
                        duration_ms=(time.time() - hook_start) * 1000,
                        result=result,
                    )
                )

            except asyncio.CancelledError:
                # 取消信号应传播，不应被吞没
                if stats:
                    stats.total_calls += 1
                    stats.failed_calls += 1
                    stats.last_call_time = time.time()
                    stats.last_error = "CancelledError"
                report.hooks_failed += 1
                logger.warning(f"Hook {hook_id} cancelled at {point_value}")
                raise  # 传播取消信号

            except Exception as e:
                # 钩子失败处理
                if stats:
                    stats.total_calls += 1
                    stats.failed_calls += 1
                    stats.last_call_time = time.time()
                    stats.last_error = str(e)[:500]

                report.hooks_failed += 1
                report.results.append(
                    HookExecutionResult(
                        hook_id=hook_id,
                        status="failed",
                        duration_ms=(time.time() - hook_start) * 1000,
                        error=str(e)[:500],
                    )
                )

                logger.warning(
                    f"Hook {hook_id} failed at {point_value}: "
                    f"{type(e).__name__}: {str(e)[:100]}"
                )

                if fail_fast:
                    break

        report.total_duration_ms = (time.time() - start_time) * 1000

        # 更新全局统计
        self._global_stats["total_triggers"] += 1
        self._global_stats["total_executions"] += report.hooks_executed
        self._global_stats["total_failures"] += report.hooks_failed

        return report

    def trigger_sync(
        self,
        hook_point: HookPoint | str,
        context: dict[str, Any],
    ) -> HookTriggerReport:
        """同步触发钩子（阻塞版本）

        注意：只能用于同步回调的钩子

        Args:
            hook_point: 钩子节点名称
            context: 钩子上下文数据

        Returns:
            执行报告
        """
        point_value = (
            hook_point.value if isinstance(hook_point, HookPoint) else hook_point
        )

        if point_value not in self._hooks:
            return HookTriggerReport(
                hook_point=point_value,
                hooks_count=0,
                hooks_executed=0,
                hooks_failed=0,
                hooks_skipped=0,
            )

        hooks = self._hooks[point_value]
        report = HookTriggerReport(
            hook_point=point_value,
            hooks_count=len(hooks),
            hooks_executed=0,
            hooks_failed=0,
            hooks_skipped=0,
        )

        start_time = time.time()

        for _, callback, hook_id in hooks:
            hook_start = time.time()
            stats = self._hook_stats.get(hook_id)

            try:
                # 同步执行
                result = callback(context)

                if stats:
                    stats.total_calls += 1
                    stats.success_calls += 1
                    stats.last_call_time = time.time()
                    stats.total_duration_ms += (time.time() - hook_start) * 1000

                report.hooks_executed += 1
                report.results.append(
                    HookExecutionResult(
                        hook_id=hook_id,
                        status="success",
                        duration_ms=(time.time() - hook_start) * 1000,
                        result=result,
                    )
                )

            except Exception as e:
                if stats:
                    stats.total_calls += 1
                    stats.failed_calls += 1
                    stats.last_error = str(e)[:500]

                report.hooks_failed += 1
                report.results.append(
                    HookExecutionResult(
                        hook_id=hook_id,
                        status="failed",
                        duration_ms=(time.time() - hook_start) * 1000,
                        error=str(e)[:500],
                    )
                )

                logger.warning(f"Hook {hook_id} failed: {type(e).__name__}: {e}")

        report.total_duration_ms = (time.time() - start_time) * 1000
        return report

    # === 查询 ===

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

    # === 辅助 ===

    def get_hook_points(self) -> list[str]:
        """获取所有钩子节点"""
        return list(self._hooks.keys())

    def get_hook_point_description(self, hook_point: str) -> str:
        """获取钩子节点描述"""
        return HOOK_POINT_DESCRIPTIONS.get(hook_point, "未知节点")