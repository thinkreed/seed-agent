"""
生命周期钩子模块

基于 Harness Engineering "确定性生命周期钩子" 设计：
- 在智能体生命周期的关键节点自动触发预设动作
- 由系统确保关键流程被执行，不依赖可能被模型遗忘的指令
- 支持动态注册、优先级管理、执行统计

核心特性：
- 统一注册体系：所有钩子集中管理
- 优先级执行：数值越小越先执行
- 执行统计：调用次数、成功/失败率
- 失败处理：钩子失败不中断主流程
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, overload

logger = logging.getLogger(__name__)


class HookPoint(str, Enum):
    """钩子节点枚举

    定义智能体生命周期的所有关键节点
    """

    # 会话生命周期
    SESSION_START = "session_start"  # 会话开始
    SESSION_END = "session_end"  # 会话结束
    SESSION_PAUSE = "session_pause"  # 会话暂停
    SESSION_RESUME = "session_resume"  # 会话恢复

    # 工具执行生命周期
    TOOL_CALL_BEFORE = "tool_call_before"  # 工具调用前
    TOOL_CALL_AFTER = "tool_call_after"  # 工具调用后
    TOOL_CALL_ERROR = "tool_call_error"  # 工具调用错误

    # LLM 调用生命周期
    LLM_CALL_BEFORE = "llm_call_before"  # LLM 调用前
    LLM_CALL_AFTER = "llm_call_after"  # LLM 调用后
    LLM_STREAM_START = "llm_stream_start"  # LLM 流式响应开始
    LLM_STREAM_CHUNK = "llm_stream_chunk"  # LLM 流式响应块
    LLM_STREAM_END = "llm_stream_end"  # LLM 流式响应结束

    # 响应生命周期
    RESPONSE_BEFORE = "response_before"  # 响应生成前
    RESPONSE_AFTER = "response_after"  # 响应生成后

    # 上下文生命周期
    CONTEXT_RESET_BEFORE = "context_reset_before"  # 上下文重置前
    CONTEXT_RESET_AFTER = "context_reset_after"  # 上下文重置后
    SUMMARY_GENERATED = "summary_generated"  # 摘要生成后

    # 子代理生命周期
    SUBAGENT_SPAWN = "subagent_spawn"  # 子代理创建
    SUBAGENT_START = "subagent_start"  # 子代理开始执行
    SUBAGENT_END = "subagent_end"  # 子代理执行结束
    SUBAGENT_ERROR = "subagent_error"  # 子代理执行错误

    # Ralph Loop 生命周期
    RALPH_ITERATION_START = "ralph_iteration_start"  # Ralph 迭代开始
    RALPH_ITERATION_END = "ralph_iteration_end"  # Ralph 迭代结束
    RALPH_COMPLETION_CHECK = "ralph_completion_check"  # Ralph 完成检查
    RALPH_CONTEXT_RESET = "ralph_context_reset"  # Ralph 上下文重置

    # Ask User 生命周期（新增）
    USER_QUESTION = "user_question"  # 发起用户问题
    USER_WAITING = "user_waiting"  # 等待用户响应
    USER_RESPONSE = "user_response"  # 用户响应接收
    USER_CANCELLED = "user_cancelled"  # 用户取消

    # 执行控制生命周期（新增）
    EXECUTION_CANCEL = "execution_cancel"  # 执行被取消
    EXECUTION_PAUSE = "execution_pause"  # 执行暂停
    EXECUTION_RESUME = "execution_resume"  # 执行恢复

    # 后台任务生命周期（新增）
    TASK_START = "task_start"  # 后台任务开始
    TASK_END = "task_end"  # 后台任务结束
    TASK_CANCEL = "task_cancel"  # 后台任务取消
    TASK_ERROR = "task_error"  # 后台任务错误
    GRACE_PERIOD_START = "grace_period_start"  # 优雅期开始
    GRACE_PERIOD_END = "grace_period_end"  # 优雅期结束

    # 关闭生命周期（新增）
    SHUTDOWN_START = "shutdown_start"  # 关闭开始
    SHUTDOWN_COMPLETE = "shutdown_complete"  # 关闭完成


@dataclass
class HookExecutionResult:
    """单个钩子执行结果"""

    hook_id: str
    status: str  # "success" | "failed" | "skipped"
    duration_ms: float
    result: Any | None = None
    error: str | None = None


@dataclass
class HookTriggerReport:
    """钩子触发报告"""

    hook_point: str
    hooks_count: int
    hooks_executed: int
    hooks_failed: int
    hooks_skipped: int
    results: list[HookExecutionResult] = field(default_factory=list)
    total_duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "hook_point": self.hook_point,
            "hooks_count": self.hooks_count,
            "hooks_executed": self.hooks_executed,
            "hooks_failed": self.hooks_failed,
            "hooks_skipped": self.hooks_skipped,
            "total_duration_ms": self.total_duration_ms,
            "results": [
                {
                    "hook_id": r.hook_id,
                    "status": r.status,
                    "duration_ms": r.duration_ms,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


@dataclass
class HookStats:
    """钩子执行统计"""

    hook_id: str
    hook_point: str
    priority: int
    total_calls: int = 0
    success_calls: int = 0
    failed_calls: int = 0
    skipped_calls: int = 0
    total_duration_ms: float = 0.0
    last_call_time: float | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "hook_id": self.hook_id,
            "hook_point": self.hook_point,
            "priority": self.priority,
            "total_calls": self.total_calls,
            "success_calls": self.success_calls,
            "failed_calls": self.failed_calls,
            "skipped_calls": self.skipped_calls,
            "success_rate": self.success_calls / self.total_calls
            if self.total_calls > 0
            else 0.0,
            "avg_duration_ms": self.total_duration_ms / self.total_calls
            if self.total_calls > 0
            else 0.0,
            "last_call_time": self.last_call_time,
            "last_error": self.last_error,
        }


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

    # 钩子节点描述
    HOOK_POINT_DESCRIPTIONS: dict[str, str] = {
        HookPoint.SESSION_START.value: "会话开始",
        HookPoint.SESSION_END.value: "会话结束",
        HookPoint.SESSION_PAUSE.value: "会话暂停",
        HookPoint.SESSION_RESUME.value: "会话恢复",
        HookPoint.TOOL_CALL_BEFORE.value: "工具调用前",
        HookPoint.TOOL_CALL_AFTER.value: "工具调用后",
        HookPoint.TOOL_CALL_ERROR.value: "工具调用错误",
        HookPoint.LLM_CALL_BEFORE.value: "LLM 调用前",
        HookPoint.LLM_CALL_AFTER.value: "LLM 调用后",
        HookPoint.LLM_STREAM_START.value: "LLM 流式响应开始",
        HookPoint.LLM_STREAM_CHUNK.value: "LLM 流式响应块",
        HookPoint.LLM_STREAM_END.value: "LLM 流式响应结束",
        HookPoint.RESPONSE_BEFORE.value: "响应生成前",
        HookPoint.RESPONSE_AFTER.value: "响应生成后",
        HookPoint.CONTEXT_RESET_BEFORE.value: "上下文重置前",
        HookPoint.CONTEXT_RESET_AFTER.value: "上下文重置后",
        HookPoint.SUMMARY_GENERATED.value: "摘要生成后",
        HookPoint.SUBAGENT_SPAWN.value: "子代理创建",
        HookPoint.SUBAGENT_START.value: "子代理开始执行",
        HookPoint.SUBAGENT_END.value: "子代理执行结束",
        HookPoint.SUBAGENT_ERROR.value: "子代理执行错误",
        HookPoint.RALPH_ITERATION_START.value: "Ralph 迭代开始",
        HookPoint.RALPH_ITERATION_END.value: "Ralph 迭代结束",
        HookPoint.RALPH_COMPLETION_CHECK.value: "Ralph 完成检查",
        HookPoint.RALPH_CONTEXT_RESET.value: "Ralph 上下文重置",
        # Ask User 生命周期
        HookPoint.USER_QUESTION.value: "发起用户问题",
        HookPoint.USER_WAITING.value: "等待用户响应",
        HookPoint.USER_RESPONSE.value: "用户响应接收",
        HookPoint.USER_CANCELLED.value: "用户取消",
        # 执行控制生命周期
        HookPoint.EXECUTION_CANCEL.value: "执行被取消",
        HookPoint.EXECUTION_PAUSE.value: "执行暂停",
        HookPoint.EXECUTION_RESUME.value: "执行恢复",
        # 后台任务生命周期
        HookPoint.TASK_START.value: "后台任务开始",
        HookPoint.TASK_END.value: "后台任务结束",
        HookPoint.TASK_CANCEL.value: "后台任务取消",
        HookPoint.TASK_ERROR.value: "后台任务错误",
        HookPoint.GRACE_PERIOD_START.value: "优雅期开始",
        HookPoint.GRACE_PERIOD_END.value: "优雅期结束",
        # 关闭生命周期
        HookPoint.SHUTDOWN_START.value: "关闭开始",
        HookPoint.SHUTDOWN_COMPLETE.value: "关闭完成",
    }

    def __init__(self):
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
        for _, hooks in self._hooks.items():
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
        return self.HOOK_POINT_DESCRIPTIONS.get(hook_point, "未知节点")


# === 全局注册中心 ===

_global_registry_instance: LifecycleHookRegistry | None = None


def get_global_registry() -> LifecycleHookRegistry:
    """获取全局钩子注册中心"""
    global _global_registry_instance
    if _global_registry_instance is None:
        _global_registry_instance = LifecycleHookRegistry()
    return _global_registry_instance


def reset_global_registry() -> None:
    """重置全局钩子注册中心"""
    global _global_registry_instance
    if _global_registry_instance:
        _global_registry_instance.clear_hooks()
    _global_registry_instance = LifecycleHookRegistry()
