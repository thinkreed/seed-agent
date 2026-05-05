"""
单用途工具工厂 - SinglePurposeToolFactory

将通用 Shell 操作封装为专用工具，提高安全性和可控性

设计原则:
- 单一职责：每个工具只做一件事
- 参数验证：严格验证输入参数
- 风险预设：预定义风险等级
- 安全封装：不暴露通用 Shell

参考来源: Harness Engineering "单用途工具设计"

重构说明:
- 原文件已拆分为多个子模块放置在 src/security/single_purpose/ 目录下
- 本文件作为向后兼容的公共 API 入口
- 内部实现已迁移至子模块
"""

# 从子模块导入所有公共接口，保持向后兼容
from src.security.single_purpose import (
    SINGLE_PURPOSE_TOOLS,
    SinglePurposeToolConfig,
    SinglePurposeToolFactory,
    SinglePurposeToolRisk,
)

__all__ = [
    "SinglePurposeToolRisk",
    "SinglePurposeToolConfig",
    "SINGLE_PURPOSE_TOOLS",
    "SinglePurposeToolFactory",
]