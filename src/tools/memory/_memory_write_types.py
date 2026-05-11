"""记忆写入类型定义

Wiki 知识落地 P2 (GenericAgent): 行动验证原则
"""

from dataclasses import dataclass
from enum import Enum


class VerifiedSource(Enum):
    """验证来源类型

    GenericAgent 行动验证原则：
    - No Execution, No Memory
    - 任何写入 L1/L2/L3 的信息，必须源自成功的工具调用结果
    """

    # 允许的来源（可以写入 L1/L2/L3）
    TOOL_CALL_SUCCESS = "tool_call_success"  # 成功的工具调用结果
    EXTERNAL_VERIFICATION = "external_verification"  # 外部验证（用户确认）
    READ_FROM_FILE = "read_from_file"  # 从文件读取（只读操作）
    SYSTEM_INIT = "system_init"  # 系统初始化配置
    AUTODREAM = "autodream"  # 定时记忆整理任务（系统自动执行）

    # 禁止的来源（不允许写入 L1/L2/L3，只能写入 L4）
    MODEL_INFERENCE = "model_inference"  # 模型推理/猜测
    PLANNING = "planning"  # 未执行的计划
    UNVERIFIED = "unverified"  # 未验证的信息


# 允许写入 L1/L2/L3 的来源
ALLOWED_SOURCES_FOR_L1L2L3 = {
    VerifiedSource.TOOL_CALL_SUCCESS,
    VerifiedSource.EXTERNAL_VERIFICATION,
    VerifiedSource.READ_FROM_FILE,
    VerifiedSource.SYSTEM_INIT,
    VerifiedSource.AUTODREAM,
}

# 禁止的来源（只能写入 L4）
DENIED_SOURCES_FOR_L1L2L3 = {
    VerifiedSource.MODEL_INFERENCE,
    VerifiedSource.PLANNING,
    VerifiedSource.UNVERIFIED,
}


@dataclass
class ValidationResult:
    """验证结果"""

    allowed: bool
    reason: str
    fallback_level: str | None = None  # 建议的降级层级


__all__ = [
    "ALLOWED_SOURCES_FOR_L1L2L3",
    "DENIED_SOURCES_FOR_L1L2L3",
    "ValidationResult",
    "VerifiedSource",
]