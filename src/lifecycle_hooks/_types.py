"""生命周期钩子类型定义

导入聚合文件，从子模块导入所有类型。
重构拆分：
- _output_types: Hook 输出类
- _hook_point: 钩子节点枚举
- _execution_types: 执行结果和统计
- _message_bus_types: MessageBus 类型
"""

from src.lifecycle_hooks._execution_types import (
    HookExecutionResult,
    HookStats,
    HookTriggerReport,
)
from src.lifecycle_hooks._hook_point import HOOK_POINT_DESCRIPTIONS, HookPoint
from src.lifecycle_hooks._message_bus_types import PendingRequest
from src.lifecycle_hooks._output_types import (
    DefaultHookOutput,
    LLMStreamHookOutput,
    PostToolUseHookOutput,
    PreToolUseHookOutput,
    UserResponseHookOutput,
)

# 导出列表（供外部导入）
__all__ = [
    # Hook 输出类
    "DefaultHookOutput",
    "PreToolUseHookOutput",
    "PostToolUseHookOutput",
    "LLMStreamHookOutput",
    "UserResponseHookOutput",
    # 钩子节点
    "HookPoint",
    # 钩子结果
    "HookExecutionResult",
    "HookTriggerReport",
    "HookStats",
    # MessageBus 类型
    "PendingRequest",
    # 常量
    "HOOK_POINT_DESCRIPTIONS",
]