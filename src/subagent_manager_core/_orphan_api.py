"""
Orphan Reaper 全局辅助函数

提供全局孤儿回收器实例的便捷访问。
"""

from ._orphan_reaper import OrphanReaper

# 全局默认实例
_global_reaper: OrphanReaper | None = None


def get_orphan_reaper() -> OrphanReaper:
    """获取全局孤儿回收器"""
    global _global_reaper
    if _global_reaper is None:
        _global_reaper = OrphanReaper()
    return _global_reaper


async def start_orphan_reaper() -> None:
    """启动全局孤儿回收器"""
    await get_orphan_reaper().start()


async def stop_orphan_reaper() -> None:
    """停止全局孤儿回收器"""
    global _global_reaper
    if _global_reaper:
        await _global_reaper.stop()