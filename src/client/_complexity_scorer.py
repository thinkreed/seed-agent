"""复杂度评分核心模块 - 基于 23 维度评估任务复杂度，决定模型路由 Tier"""

import logging
import math
from typing import Any

from src.client._complexity_analyzer import ComplexityAnalyzer
from src.client._complexity_types import (
    DIMENSION_CONFIGS, TIER_RANGES, ComplexityDimension, ComplexityScore, ComplexityTier,
)

logger = logging.getLogger("seed_agent")


class ComplexityScorer:
    """复杂度评分器 - 基于 23 维度评估任务复杂度，决定模型路由 Tier

    Tier Floor 机制：
    - 有 Tools 时强制提升到至少 STANDARD
    - 多个 Tools 时提升到 COMPLEX
    - 复杂工具（执行、沙箱）时提升到 REASONING
    """

    def __init__(self):
        self._dimensions = self._init_dimensions()
        self._analyzer = ComplexityAnalyzer(self._dimensions, self._set_dimension)

    def _init_dimensions(self) -> dict[str, ComplexityDimension]:
        """初始化维度"""
        return {
            name: ComplexityDimension(name=name, weight=weight, threshold=threshold)
            for name, (weight, threshold) in DIMENSION_CONFIGS.items()
        }

    def score_messages(
        self,
        messages: list[dict],
        has_tools: bool = False,
        specificity_type: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> ComplexityScore:
        """评分消息列表，返回 ComplexityScore 结果"""
        self._reset_dimensions()

        # 分析维度（委托给分析器）
        self._analyzer.analyze_code_complexity(messages, context)
        self._analyzer.analyze_task_complexity(messages, context)
        self._analyzer.analyze_context_complexity(messages, context)
        self._analyzer.analyze_tool_complexity(messages, has_tools, context)
        self._analyzer.analyze_knowledge_complexity(messages, context)

        # 计算总分
        raw_score = sum(dim.normalized * dim.weight for dim in self._dimensions.values())
        confidence = self._sigmoid_confidence(raw_score)
        tier = self._determine_tier(raw_score)

        # 应用 Tier Floor
        tier, tier_floor_applied = self._apply_tier_floor(
            tier, has_tools, self._get_tool_complexity_score())

        return ComplexityScore(
            tier=tier,
            raw_score=raw_score,
            confidence=confidence,
            dimensions=dict(self._dimensions),
            has_tools=has_tools,
            specificity_type=specificity_type,
            tier_floor_applied=tier_floor_applied,
            metadata=context or {},
        )

    def _reset_dimensions(self) -> None:
        """重置所有维度值"""
        for dim in self._dimensions.values():
            dim.value = 0.0
            dim.normalized = 0.0

    def _set_dimension(self, name: str, value: float) -> None:
        """设置维度值"""
        if name in self._dimensions:
            dim = self._dimensions[name]
            dim.value = value
            dim.normalized = min(value / dim.threshold, 1.0)

    def _sigmoid_confidence(self, score: float) -> float:
        """Sigmoid 置信度平滑"""
        k, x0 = 0.3, 5.0  # 增益系数和中点
        return 1.0 / (1.0 + math.exp(-k * (score - x0)))

    def _determine_tier(self, score: float) -> ComplexityTier:
        """确定 Tier"""
        for tier, (low, high) in TIER_RANGES.items():
            if low <= score < high:
                return tier
        return ComplexityTier.REASONING

    def _apply_tier_floor(
        self, tier: ComplexityTier, has_tools: bool, tool_score: float,
    ) -> tuple[ComplexityTier, bool]:
        """应用 Tier Floor 机制"""
        if not has_tools:
            return tier, False

        tier_order = list(ComplexityTier)
        current_idx = tier_order.index(tier)

        # 工具数 >= 3 或复杂工具时提升到 REASONING
        if tool_score >= 2.0 or self._dimensions["tool_count"].value >= 3:
            min_tier = ComplexityTier.REASONING
        elif self._dimensions["tool_count"].value >= 1:
            min_tier = ComplexityTier.STANDARD
        else:
            return tier, False

        min_idx = tier_order.index(min_tier)
        return (min_tier, True) if min_idx > current_idx else (tier, False)

    def _get_tool_complexity_score(self) -> float:
        """获取工具复杂度得分"""
        return (
            self._dimensions["tool_count"].normalized +
            self._dimensions["tool_types"].normalized +
            self._dimensions["cross_domain_calls"].normalized +
            self._dimensions["permission_level"].normalized
        )