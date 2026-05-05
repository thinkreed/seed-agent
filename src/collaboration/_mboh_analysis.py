"""多智能体协作模块 - 多脑一手分析（混入类）

包含 MultiBrainOneHandOrchestrator 的分析方法混入类。

版本: v2.0 (重构实现)
创建日期: 2026-05-05
"""

from src.collaboration._mboh_analysis_methods import (
    _analyze_with_perspective,
    _parse_issues,
    _parse_suggestions,
    _read_target,
    analyze_from_multiple_angles,
)
from src.collaboration._mboh_core import MultiBrainOneHandOrchestrator
from src.collaboration._mboh_improve_methods import (
    _execute_improvements,
    _merge_suggestions,
    _parse_actions,
    collaborative_improve,
)


class MultiBrainOneHandAnalysisMixin:
    """多脑一手分析方法混入类

    将分析方法注入到 MultiBrainOneHandOrchestrator。
    """

    # 绑定分析方法
    analyze_from_multiple_angles = analyze_from_multiple_angles
    _read_target = _read_target
    _analyze_with_perspective = _analyze_with_perspective
    _parse_issues = _parse_issues
    _parse_suggestions = _parse_suggestions

    # 绑定改进方法
    collaborative_improve = collaborative_improve
    _merge_suggestions = _merge_suggestions
    _parse_actions = _parse_actions
    _execute_improvements = _execute_improvements


__all__ = ["MultiBrainOneHandAnalysisMixin"]