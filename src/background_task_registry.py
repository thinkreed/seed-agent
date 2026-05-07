"""
后台任务注册表模块

基于 qwen-code 的 background-tasks.ts 设计：
- 每个后台任务关联一个 AbortController
- cancel() 发送取消信号
- 优雅期让自然完成优先
- 状态持久化和恢复

核心特性：
- 任务生命周期管理
- 取消信号传播
- 优雅期竞争处理
- 任务状态查询

参考：
- qwen-code: background-tasks.ts

此模块作为 facade，从 background_task_registry/ 子包导入所有功能以保持向后兼容。
"""

# 从 background_task_registry 子包导入所有功能
from src.background_task_registry import (
    BackgroundTaskEntry,
    BackgroundTaskRegistry,
    TaskStatus,
    get_background_task_registry,
    init_background_task_registry,
    reset_background_task_registry,
)

# 导出常量
from src.background_task_registry._types import CANCEL_GRACE_SECONDS

__all__ = [
    "CANCEL_GRACE_SECONDS",
    "BackgroundTaskEntry",
    "BackgroundTaskRegistry",
    "TaskStatus",
    "get_background_task_registry",
    "init_background_task_registry",
    "reset_background_task_registry",
]