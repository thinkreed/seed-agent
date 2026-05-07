"""
命令风险分类器 - 兼容性入口

原 risk_classifier.py 已重构为 risk_classifier_core/ package。
此文件保持向后兼容，从 package 导入主类。

模块拆分:
- _types.py: 枚举、配置表、结果类型
- _factors.py: 参数风险因素配置
- _classifier.py: 核心分类逻辑

参考来源: Harness Engineering "工具与权限"
"""

# 从 package 导入，保持向后兼容
from src.security.risk_classifier_core import (
    ISOLATION_LEVEL_MODIFIERS,
    PARAM_RISK_FACTORS,
    RISK_LEVEL_CONFIGS,
    TOOL_BASE_RISKS,
    USER_LEVEL_MODIFIERS,
    ClassificationResult,
    CommandRiskClassifier,
    RiskAction,
    RiskLevel,
    RiskLevelConfig,
    analyze_param_risk,
    check_code_risk,
    check_path_risk,
)

__all__ = [
    "ISOLATION_LEVEL_MODIFIERS",
    "PARAM_RISK_FACTORS",
    "RISK_LEVEL_CONFIGS",
    "TOOL_BASE_RISKS",
    "USER_LEVEL_MODIFIERS",
    "ClassificationResult",
    "CommandRiskClassifier",
    "RiskAction",
    "RiskLevel",
    "RiskLevelConfig",
    "analyze_param_risk",
    "check_code_risk",
    "check_path_risk",
]