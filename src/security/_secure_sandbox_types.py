"""
安全沙盒类型定义

包含数据类定义
"""

from dataclasses import dataclass

from src.security.risk_classifier import RiskAction, RiskLevel


@dataclass
class SecureExecutionResult:
    """安全执行结果"""

    tool_call_id: str
    content: str
    success: bool
    risk_level: RiskLevel | None = None
    action_taken: RiskAction | None = None
    duration_ms: float = 0.0
    blocked: bool = False
    user_confirmed: bool | None = None