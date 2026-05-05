"""后台任务注册表模块

基于 qwen-code 的 background-tasks.ts 设计：
- 每个后台任务关联一个 AbortController
- cancel() 发送取消信号
- 优雅期让自然完成优先
- 状态持久化和恢复
"""

import threading

from src.background_task_registry._registry_class import BackgroundTaskRegistry
from src.background_task_registry._types import BackgroundTaskEntry, TaskStatus

# 全局注册表
_global_registry: BackgroundTaskRegistry | None = None
_registry_lock = threading.Lock()


def get_background_task_registry() -> BackgroundTaskRegistry:
    """获取全局后台任务注册表（线程安全）"""
    global _global_registry
    if _global_registry is None:
        with _registry_lock:
            if _global_registry is None:
                _global_registry = BackgroundTaskRegistry()
    return _global_registry


def init_background_task_registry(
    max_concurrent: int = 3,
) -> BackgroundTaskRegistry:
    """初始化全局注册表

    Args:
        max_concurrent: 最大并发任务数

    Returns:
        注册表实例
    """
    global _global_registry
    _global_registry = BackgroundTaskRegistry(max_concurrent=max_concurrent)
    return _global_registry


def reset_background_task_registry() -> None:
    """重置全局注册表"""
    global _global_registry
    if _global_registry:
        _global_registry.cancel_all()
        _global_registry.cleanup()
    _global_registry = BackgroundTaskRegistry()


__all__ = [
    "BackgroundTaskRegistry",
    "BackgroundTaskEntry",
    "TaskStatus",
    "get_background_task_registry",
    "init_background_task_registry",
    "reset_background_task_registry",
]