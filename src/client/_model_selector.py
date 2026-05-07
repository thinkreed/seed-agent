"""
复杂度 Tier 模型选择器

根据 ComplexityTier 选择对应的模型。
"""

from src.client._complexity_types import ComplexityTier

# 默认 Tier 到模型映射
DEFAULT_TIER_MODEL_MAPPING: dict[ComplexityTier, str] = {
    ComplexityTier.SIMPLE: "gpt-4o-mini",
    ComplexityTier.STANDARD: "gpt-4o",
    ComplexityTier.COMPLEX: "claude-3-5-sonnet",
    ComplexityTier.REASONING: "claude-3-opus",
}


def select_model_for_tier(
    tier: ComplexityTier,
    model_mapping: dict[ComplexityTier, str] | None = None,
) -> str:
    """根据 Tier 选择模型

    Args:
        tier: 复杂度层级
        model_mapping: Tier 到模型的映射

    Returns:
        模型 ID
    """
    mapping = model_mapping or DEFAULT_TIER_MODEL_MAPPING
    return mapping.get(tier, DEFAULT_TIER_MODEL_MAPPING[ComplexityTier.STANDARD])


def get_tier_model_mapping() -> dict[ComplexityTier, str]:
    """获取默认 Tier 模型映射"""
    return DEFAULT_TIER_MODEL_MAPPING.copy()