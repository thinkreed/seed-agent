"""
生命周期钩子模块（代理导入）

此文件已重构为模块化结构，原内容拆分到 src/lifecycle_hooks/ 子目录。
导入路径保持不变，确保向后兼容。

新结构:
- _types.py: HookPoint, HookExecutionResult, HookTriggerReport, HookStats
- _registry.py: LifecycleHookRegistry
- _global.py: get_global_registry, reset_global_registry
"""

# 从模块导入所有公共接口
from src.lifecycle_hooks import (
    HookExecutionResult,
    HookPoint,
    HookStats,
    HookTriggerReport,
    LifecycleHookRegistry,
    get_global_registry,
    reset_global_registry,
    HOOK_POINT_DESCRIPTIONS,
)

__all__ = [
    "HookPoint",
    "HookExecutionResult",
    "HookTriggerReport",
    "HookStats",
    "LifecycleHookRegistry",
    "get_global_registry",
    "reset_global_registry",
    "HOOK_POINT_DESCRIPTIONS",
]