"""生命周期钩子异步触发模块

包含异步触发方法 trigger。
"""

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from src.lifecycle_hooks._types import (
    HookExecutionResult,
    HookPoint,
    HookTriggerReport,
)

logger = logging.getLogger(__name__)


class AsyncTriggerMixin:
    """异步触发方法 mixin

    提供 trigger 方法。
    需要 _hooks 和 _hook_stats 属性。
    """

    _hooks: dict[str, list[tuple[int, Callable, str]]]
    _hook_stats: dict[str, Any]
    _global_stats: dict[str, Any]

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
                # 取消信号应传播
                if stats:
                    stats.total_calls += 1
                    stats.failed_calls += 1
                    stats.last_call_time = time.time()
                    stats.last_error = "CancelledError"
                report.hooks_failed += 1
                logger.warning(f"Hook {hook_id} cancelled at {point_value}")
                raise

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


__all__ = ["AsyncTriggerMixin"]