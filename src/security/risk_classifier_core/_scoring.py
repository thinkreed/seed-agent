"""
风险分数计算与映射

提供风险等级映射和修正因子计算函数
"""

from src.security.risk_classifier_core._types import (
    ISOLATION_LEVEL_MODIFIERS,
    TOOL_BASE_RISKS,
    USER_LEVEL_MODIFIERS,
    RiskLevel,
)


def score_to_level(score: float) -> RiskLevel:
    """分数映射到风险等级

    Args:
        score: 风险分数 (0.0+)

    Returns:
        RiskLevel: 对应的风险等级
    """
    if score < 0.3:
        return RiskLevel.SAFE
    if score < 0.6:
        return RiskLevel.CAUTION
    if score < 1.2:
        return RiskLevel.RISKY
    return RiskLevel.DANGEROUS


def get_tool_base_risk(tool_name: str) -> float:
    """获取工具基础风险分数

    Args:
        tool_name: 工具名称

    Returns:
        float: 基础风险分数
    """
    return TOOL_BASE_RISKS.get(tool_name, TOOL_BASE_RISKS["default"])


def get_user_risk_modifier(user_level: str) -> float:
    """获取用户权限等级风险修正

    Args:
        user_level: 用户权限等级

    Returns:
        float: 风险修正值 (正数增加风险, 负数降低风险)
    """
    return USER_LEVEL_MODIFIERS.get(user_level, 0.0)


def get_isolation_risk_modifier(isolation_level: str) -> float:
    """获取 Sandbox 隔离等级风险修正

    Args:
        isolation_level: 隔离等级 (vm/container/process/none)

    Returns:
        float: 风险修正值 (正数增加风险, 负数降低风险)
    """
    return ISOLATION_LEVEL_MODIFIERS.get(isolation_level, 0.0)


def calculate_final_score(
    base_risk: float,
    param_risk: float,
    user_modifier: float,
    isolation_modifier: float,
) -> float:
    """计算最终风险分数

    Args:
        base_risk: 工具基础风险
        param_risk: 参数风险
        user_modifier: 用户权限修正
        isolation_modifier: 隔离等级修正

    Returns:
        float: 最终风险分数 (>= 0)
    """
    final_score = base_risk + param_risk + user_modifier + isolation_modifier
    return max(0.0, final_score)