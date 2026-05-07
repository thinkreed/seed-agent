"""多智能体协作模块 - 多脑一手编排器

MultiBrainOneHandOrchestrator: 多脑一手编排器

适用场景：多角度分析同一份代码（安全审查 + 性能优化）

核心特性：
- 共享 Sandbox：所有大脑在同一工作台操作
- 多视角分析：每个大脑从不同角度分析
- 协作改进：融合建议后执行改进

版本: v2.0 (重构实现)
创建日期: 2026-05-05
"""

# 导入核心类和分析混入
from src.collaboration._mboh_analysis import MultiBrainOneHandAnalysisMixin
from src.collaboration._mboh_core import (
    MultiBrainOneHandOrchestrator as _CoreOrchestrator,
)


class MultiBrainOneHandOrchestrator(_CoreOrchestrator, MultiBrainOneHandAnalysisMixin):
    """多脑一手编排器：多个 Claude 共享一个 Sandbox

    组合核心定义和分析方法混入。

    适用场景：多角度分析同一份代码（安全审查 + 性能优化）
    """

    pass


# 导出类
__all__ = ["MultiBrainOneHandOrchestrator"]