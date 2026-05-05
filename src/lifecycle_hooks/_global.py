"""
全局生命周期钩子注册中心管理

提供线程安全的全局注册中心访问和重置功能。
"""

import threading

from src.lifecycle_hooks._registry import LifecycleHookRegistry

_global_registry_instance: LifecycleHookRegistry | None = None
_registry_lock = threading.Lock()


def get_global_registry() -> LifecycleHookRegistry:
    """获取全局钩子注册中心（线程安全）"""
    global _global_registry_instance
    if _global_registry_instance is None:
        with _registry_lock:
            if _global_registry_instance is None:
                _global_registry_instance = LifecycleHookRegistry()
    return _global_registry_instance


def reset_global_registry() -> None:
    """重置全局钩子注册中心"""
    global _global_registry_instance
    if _global_registry_instance:
        _global_registry_instance.clear_hooks()
    _global_registry_instance = LifecycleHookRegistry()