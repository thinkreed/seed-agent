"""生命周期钩子触发方法模块

包含钩子触发执行相关方法：
- trigger (异步触发)
- trigger_sync (同步触发)

此模块作为 facade，从子模块导入所有功能以保持向后兼容。
"""

from src.lifecycle_hooks._async_trigger import AsyncTriggerMixin
from src.lifecycle_hooks._sync_trigger import SyncTriggerMixin


# 组合两个 mixin
class TriggerMixin(AsyncTriggerMixin, SyncTriggerMixin):
    """钩子触发方法 mixin

    组合异步和同步触发功能。
    """
    pass


__all__ = ["AsyncTriggerMixin", "SyncTriggerMixin", "TriggerMixin"]