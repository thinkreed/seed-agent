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
- CommandHookRunner: 命令钩子执行器（新增 P2）
- HttpHookRunner: HTTP 钩子执行器（新增 P2）
"""

# 类型导出
# Wiki 知识落地: 命令/HTTP 钩子 (Qwen-Code P2)
from src.lifecycle_hooks._command_runner import (
    CommandHookConfig,
    CommandHookResult,
    CommandHookRunner,
)

# 全局管理导出
from src.lifecycle_hooks._global import (
    get_global_registry,
    reset_global_registry,
)
from src.lifecycle_hooks._http_runner import (
    HttpHookConfig,
    HttpHookResult,
    HttpHookRunner,
    execute_http_hook_sync,
)

# Wiki 知识落地: MessageBus 导出
from src.lifecycle_hooks._message_bus import (
    HookAggregator,
    LifecycleMessageBus,
    PermissionDecision,
    get_message_bus,
    reset_message_bus,
)

# 注册中心导出
from src.lifecycle_hooks._registry import LifecycleHookRegistry
from src.lifecycle_hooks._types import (
    HOOK_POINT_DESCRIPTIONS,
    DefaultHookOutput,
    HookExecutionResult,
    HookPoint,
    HookStats,
    HookTriggerReport,
    LLMStreamHookOutput,
    PostToolUseHookOutput,
    PreToolUseHookOutput,
    UserResponseHookOutput,
)

__all__ = [
    "HOOK_POINT_DESCRIPTIONS",
    # Wiki 知识落地: 命令/HTTP 钩子 (Qwen-Code P2)
    "CommandHookConfig",
    "CommandHookResult",
    "CommandHookRunner",
    # Wiki 知识落地: Hook 输出类
    "DefaultHookOutput",
    "HookAggregator",
    "HookExecutionResult",
    # 类型
    "HookPoint",
    "HookStats",
    "HookTriggerReport",
    "HttpHookConfig",
    "HttpHookResult",
    "HttpHookRunner",
    "LLMStreamHookOutput",
    # 注册中心
    "LifecycleHookRegistry",
    "LifecycleMessageBus",
    # Wiki 知识落地: MessageBus
    "PermissionDecision",
    "PostToolUseHookOutput",
    "PreToolUseHookOutput",
    "UserResponseHookOutput",
    "execute_http_hook_sync",
    # 全局管理
    "get_global_registry",
    "get_message_bus",
    "reset_global_registry",
    "reset_message_bus",
]