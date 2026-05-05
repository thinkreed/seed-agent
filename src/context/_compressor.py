"""
渐进式上下文压缩模块

三层压缩策略：
- Tier 1: 最新 5 轮完整保留 (Full)
- Tier 2: 稍旧 10 轮轻量总结 (Light Summary) - 50% 容量时触发
- Tier 3: 更早历史简短摘要 (Abstract) - 75% 容量时触发

核心特性：
- 渐进信息损失，不丢失原始数据（Session 保留）
- 根据上下文使用率动态选择压缩层级

重构说明:
- 原实现已拆分为独立模块以提高可维护性
- 此文件保持向后兼容，从新模块导入所有内容

模块结构:
- _compressor_prompts.py: 提示模板
- _compressor_utils.py: 工具函数（Token估算、消息转换等）
- _compressor_tiers.py: 层级操作（Tier 1/2/3 同步/异步）
- _compressor_core.py: 核心类
"""

# 从核心模块导入主类（向后兼容）
from src.context._compressor_core import ProgressiveContextCompressor

# 从提示模块导入常量（向后兼容）
from src.context._compressor_prompts import (
    ABSTRACT_SUMMARY_PROMPT,
    LIGHT_SUMMARY_PROMPT,
)

__all__ = [
    "ProgressiveContextCompressor",
    "LIGHT_SUMMARY_PROMPT",
    "ABSTRACT_SUMMARY_PROMPT",
]