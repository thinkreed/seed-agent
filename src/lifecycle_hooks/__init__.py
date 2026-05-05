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

Wiki 知识落地 (基于 Qwen-Code Hooks 设计):
- MessageBus.request(): 请求/响应模式 + AbortSignal 支持
- HookAggregator: 多钩子结果合并，deny 优先
"""

# 类型导出
from src.lifecycle_hooks._types import (
    HookExecutionResult,
    HookPoint,
    HookStats,
    HookTriggerReport,
    HOOK_POINT_DESCRIPTIONS,
)

# 注册中心导出
from src.lifecycle_hooks._registry import LifecycleHookRegistry

# 全局管理导出
from src.lifecycle_hooks._global import (
    get_global_registry,
    reset_global_registry,
)

# Wiki 知识落地: MessageBus 导出
from src.lifecycle_hooks._message_bus import (
    PermissionDecision,
    HookAggregator,
    LifecycleMessageBus,
    get_message_bus,
    reset_message_bus,
)

__all__ = [
    # 类型
    "HookPoint",
    "HookExecutionResult",
    "HookTriggerReport",
    "HookStats",
    "HOOK_POINT_DESCRIPTIONS",
    # 注册中心
    "LifecycleHookRegistry",
    # 全局管理
    "get_global_registry",
    "reset_global_registry",
    # Wiki 知识落地: MessageBus
    "PermissionDecision",
    "HookAggregator",
    "LifecycleMessageBus",
    "get_message_bus",
    "reset_message_bus",
]