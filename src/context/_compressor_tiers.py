"""
上下文压缩层级操作

包含 Tier 1/2/3 的同步和异步压缩实现

重构说明:
- 原实现已拆分为独立模块以提高可维护性
- 此文件保持向后兼容，从新模块导入所有内容
"""

from src.context._compressor_tier_async import (
    abstract_summarize,
    apply_all_tiers_async,
    apply_tier_1_and_2_async,
    light_summarize,
)
from src.context._compressor_tier_sync import (
    apply_all_tiers_sync,
    apply_tier_1_and_2_sync,
    apply_tier_1_only,
)

__all__ = [
    "abstract_summarize",
    "apply_all_tiers_async",
    "apply_all_tiers_sync",
    "apply_tier_1_and_2_async",
    "apply_tier_1_and_2_sync",
    "apply_tier_1_only",
    "light_summarize",
]