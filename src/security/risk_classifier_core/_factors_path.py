"""
命令风险分类器 - 路径风险检测

包含:
- 路径风险检查函数
"""

from typing import Any

from ._factors_config import PARAM_RISK_FACTORS


def check_path_risk(path: str) -> tuple[float, list[str]]:
    """检查路径风险

    Returns:
        (risk_score, factor_descriptions)
    """
    risk_score = 0.0
    factors: list[str] = []

    # 路径遍历检测
    for pattern in PARAM_RISK_FACTORS["path_traversal"]["patterns"]:
        if pattern in path:
            risk_score += PARAM_RISK_FACTORS["path_traversal"]["risk_boost"]
            factors.append(f"path_traversal({pattern})")
            break

    # 系统路径检测
    for pattern in PARAM_RISK_FACTORS["system_paths"]["patterns"]:
        if pattern.lower() in path.lower():
            risk_score += PARAM_RISK_FACTORS["system_paths"]["risk_boost"]
            factors.append(f"system_path({pattern})")
            break

    # 敏感文件检测
    path_lower = path.lower()
    for pattern in PARAM_RISK_FACTORS["sensitive_files"]["path_patterns"]:
        if pattern in path_lower:
            risk_score += PARAM_RISK_FACTORS["sensitive_files"]["risk_boost"]
            factors.append(f"sensitive_file({pattern})")
            break

    return risk_score, factors