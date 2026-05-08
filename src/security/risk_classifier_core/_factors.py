"""
命令风险分类器 - 参数风险因素

包含:
- 参数风险因素配置
- 路径风险检测
- 代码风险检测
"""

from typing import Any

from ._factors_config import PARAM_RISK_FACTORS
from ._factors_path import check_path_risk

# 重新导出配置以保持 API 兼容
__all__ = ["PARAM_RISK_FACTORS", "check_path_risk", "check_code_risk", "analyze_param_risk"]


def check_code_risk(code: str) -> tuple[float, list[str]]:
    """检查代码风险

    Returns:
        (risk_score, factor_descriptions)
    """
    risk_score = 0.0
    factors: list[str] = []

    code_lower = code.lower()
    dangerous_patterns = PARAM_RISK_FACTORS["dangerous_commands"]["code_patterns"]

    for pattern in dangerous_patterns:
        if pattern.lower() in code_lower:
            risk_score += PARAM_RISK_FACTORS["dangerous_commands"]["risk_boost"]
            factors.append(f"dangerous_command({pattern})")

    return risk_score, factors


def analyze_param_risk(
    tool_name: str,
    args: dict[str, Any],
) -> tuple[float, list[str]]:
    """分析参数风险

    Returns:
        (risk_score, factor_descriptions)
    """
    risk_score = 0.0
    factors: list[str] = []

    # 路径参数检查
    path_keys = ["path", "file_path", "directory", "dir", "cwd", "src", "dst"]
    for key in path_keys:
        if key in args and isinstance(args[key], str):
            path_value = args[key]
            path_risk, path_factors = check_path_risk(path_value)
            risk_score += path_risk
            factors.extend(path_factors)

    # 参数条件检查
    for factor_name, factor_config in PARAM_RISK_FACTORS.items():
        if "param_conditions" in factor_config:
            conditions = factor_config["param_conditions"]
            for param_name, param_values in conditions.items():
                if param_name in args:
                    arg_value = args[param_name]
                    if arg_value in param_values or str(arg_value).lower() in [
                        str(v).lower() for v in param_values
                    ]:
                        risk_score += factor_config["risk_boost"]
                        factors.append(f"{factor_name}({param_name}={arg_value})")

    # 代码内容风险检查
    if tool_name in ("code_as_policy", "run_shell_command"):
        code_keys = ["code", "command", "cmd"]
        for key in code_keys:
            if key in args and isinstance(args[key], str):
                code_risk, code_factors = check_code_risk(args[key])
                risk_score += code_risk
                factors.extend(code_factors)

    return risk_score, factors