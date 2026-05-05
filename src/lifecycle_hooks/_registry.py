"""
生命周期钩子注册中心

基于 Harness Engineering "确定性生命周期钩子" 设计：
- 在智能体生命周期的关键节点自动触发预设动作
- 由系统确保关键流程被执行，不依赖可能被模型遗忘的指令
- 支持动态注册、优先级管理、执行统计
"""

import logging
from typing import Any

from src.lifecycle_hooks._query import QueryMixin
from src.lifecycle_hooks._registration import RegistrationMixin
from src.lifecycle_hooks._trigger import TriggerMixin
from src.lifecycle_hooks._types import HookPoint

logger = logging.getLogger(__name__)


class LifecycleHookRegistry(
    RegistrationMixin, TriggerMixin, QueryMixin
):
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
        self._hooks: dict[str, list[tuple[int, Any, str]]] = {
            point.value: [] for point in HookPoint
        }
        # 执行统计: {hook_id: HookStats}
        self._hook_stats: dict[str, Any] = {}
        # 全局统计
        self._global_stats: dict[str, Any] = {
            "total_triggers": 0,
            "total_executions": 0,
            "total_failures": 0,
            "total_skips": 0,
        }

        logger.info("LifecycleHookRegistry initialized")


# 为了向后兼容，导出所有相关类型
__all__ = ["LifecycleHookRegistry"]