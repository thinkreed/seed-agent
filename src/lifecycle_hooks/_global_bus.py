"""全局消息总线单例管理

提供全局 LifecycleMessageBus 实例的获取和重置功能。
"""

import logging

from src.lifecycle_hooks._message_bus_core import LifecycleMessageBus

logger = logging.getLogger(__name__)

# 全局单例
_global_message_bus: LifecycleMessageBus | None = None


def get_message_bus() -> LifecycleMessageBus:
    """获取全局消息总线

    Returns:
        LifecycleMessageBus 实例（延迟初始化）
    """
    global _global_message_bus
    if _global_message_bus is None:
        _global_message_bus = LifecycleMessageBus()
    return _global_message_bus


def reset_message_bus() -> None:
    """重置全局消息总线

    用于测试或需要完全重置状态时。
    """
    global _global_message_bus
    _global_message_bus = None


__all__ = [
    "get_message_bus",
    "reset_message_bus",
]