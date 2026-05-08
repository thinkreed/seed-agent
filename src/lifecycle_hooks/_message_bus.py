"""
Lifecycle Hooks MessageBus

基于 Qwen-Code MessageBus 设计的请求/响应模式消息总线：
- 支持 AbortSignal 取消
- 超时管理
- 多钩子结果合并

重构说明:
- PermissionDecision 从 src/tools/_types.py 导入（避免重复）
- PendingRequest 移至 _message_bus_types.py
- HookAggregator 移至 _aggregator.py
- LifecycleMessageBus 移至 _message_bus_core.py
- 全局单例管理移至 _global_bus.py
"""

# 核心实现
from src.lifecycle_hooks._message_bus_core import LifecycleMessageBus

# 类型定义
from src.lifecycle_hooks._message_bus_types import PendingRequest

# 聚合器
from src.lifecycle_hooks._aggregator import HookAggregator

# 全局单例
from src.lifecycle_hooks._global_bus import get_message_bus, reset_message_bus

# 兼容导出 (PermissionDecision 从 src.tools 重新导出)
from src.tools import PermissionDecision

__all__ = [
    "HookAggregator",
    "LifecycleMessageBus",
    "PendingRequest",
    "PermissionDecision",
    "get_message_bus",
    "reset_message_bus",
]