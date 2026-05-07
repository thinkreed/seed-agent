"""
Specificity 路由器

整合 SpecificityDetector 和 ComplexityScorer，
实现三层路由优先级：Header Tiers → Specificity → Complexity
"""

from typing import Any

from src.client._complexity_scorer import ComplexityScorer
from src.client._complexity_types import ComplexityTier
from src.client._model_selector import select_model_for_tier
from src.client._specificity_detector import SpecificityDetector
from src.client._specificity_types import SpecificityType


class SpecificityRouter:
    """Specificity 路由器

    整合 SpecificityDetector 和 ComplexityScorer，
    实现三层路由优先级：Header Tiers → Specificity → Complexity

    路由顺序:
    1. Header Tier: HTTP 头显式指定 Tier（调试/测试）
    2. Specificity: 任务类型检测路由特定模型
    3. Complexity: 复杂度评分路由 Tier 模型
    """

    def __init__(
        self,
        detector: SpecificityDetector | None = None,
        model_mapping: dict[SpecificityType, str] | None = None,
    ):
        self._detector = detector or SpecificityDetector(model_mapping)

    def route(
        self,
        messages: list[dict],
        header_tier: str | None = None,
        has_tools: bool = False,
        context: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """路由到模型

        Args:
            messages: LLM 消息列表
            header_tier: HTTP 头指定 Tier（显式控制）
            has_tools: 是否有工具调用
            context: 额外上下文

        Returns:
            (model_id, routing_info) 元组
        """
        routing_info: dict[str, Any] = {
            "header_tier": header_tier,
            "specificity": None,
            "complexity": None,
            "route_source": "unknown",
        }

        # 1. Header Tier 优先级最高
        if header_tier:
            model = self._get_model_for_header_tier(header_tier)
            routing_info["route_source"] = "header"
            routing_info["header_tier"] = header_tier
            return model, routing_info

        # 2. Specificity 检测
        spec_result = self._detector.detect(messages, context)
        routing_info["specificity"] = {
            "type": spec_result.detected_type.value,
            "confidence": spec_result.confidence,
            "keywords": spec_result.keywords_matched,
            "patterns": spec_result.patterns_matched,
        }

        # Specificity 置信度足够高时直接路由
        if spec_result.confidence >= self._detector._min_confidence:
            routing_info["route_source"] = "specificity"
            return spec_result.model_override or "gpt-4o", routing_info

        # 3. Complexity 评分
        scorer = ComplexityScorer()
        comp_result = scorer.score_messages(
            messages, has_tools, str(spec_result.detected_type), context
        )

        routing_info["complexity"] = {
            "tier": comp_result.tier.value,
            "score": comp_result.raw_score,
            "confidence": comp_result.confidence,
            "tier_floor_applied": comp_result.tier_floor_applied,
        }
        routing_info["route_source"] = "complexity"

        model = select_model_for_tier(comp_result.tier)
        return model, routing_info

    def _get_model_for_header_tier(self, header_tier: str) -> str:
        """从 Header Tier 获取模型"""
        tier_map = {
            "simple": ComplexityTier.SIMPLE,
            "standard": ComplexityTier.STANDARD,
            "complex": ComplexityTier.COMPLEX,
            "reasoning": ComplexityTier.REASONING,
        }
        tier = tier_map.get(header_tier.lower(), ComplexityTier.STANDARD)
        return select_model_for_tier(tier)


def get_specificity_detector() -> SpecificityDetector:
    """获取全局 SpecificityDetector"""
    return SpecificityDetector()


def get_specificity_router() -> SpecificityRouter:
    """获取全局 SpecificityRouter"""
    return SpecificityRouter()