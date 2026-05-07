"""
渐进式工具扩展器 - ProgressiveToolExpander

根据任务类型、用户权限、复杂度等因素动态扩展可用工具集

工具层级:
- Tier 0 Minimal: 最小工具集，只读操作
- Tier 1 Basic: 基础工具集，常用操作
- Tier 2 Extended: 扩展工具集，写入操作
- Tier 3 Full: 完整工具集，高风险操作

参考来源: Harness Engineering "渐进式工具扩展"

重构说明:
- 原实现已拆分为独立模块以提高可维护性
- 此文件保持向后兼容，从新模块导入所有内容

模块结构:
- _tool_expander_types.py: 类型定义（枚举、数据类）
- _tool_expander_config.py: 配置（层级定义、映射表）
- _tool_expander_core.py: 核心类
"""

# 从类型模块导入（向后兼容）
# 从配置模块导入（向后兼容）
from src.security._tool_expander_config import (
    TASK_TYPE_TIER_MAP,
    TOOL_TIER_CONFIGS,
    USER_PERMISSION_TIER_LIMITS,
)

# 从核心模块导入主类（向后兼容）
from src.security._tool_expander_core import ProgressiveToolExpander
from src.security._tool_expander_types import (
    ExpansionEvent,
    ToolTier,
    ToolTierConfig,
)

__all__ = [
    "TASK_TYPE_TIER_MAP",
    "TOOL_TIER_CONFIGS",
    "USER_PERMISSION_TIER_LIMITS",
    "ExpansionEvent",
    "ProgressiveToolExpander",
    "ToolTier",
    "ToolTierConfig",
]