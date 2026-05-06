"""单用途工具类型定义"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SinglePurposeToolRisk(StrEnum):
    """单用途工具风险等级"""

    SAFE = "safe"
    CAUTION = "caution"
    RISKY = "risky"
    DANGEROUS = "dangerous"


@dataclass
class SinglePurposeToolConfig:
    """单用途工具配置"""

    name: str
    description: str
    replaces_command: str  # 替代的通用命令
    risk: SinglePurposeToolRisk
    args_schema: dict[str, Any]  # 参数 schema
    require_confirmation: bool = False
    block_by_default: bool = False
    implementation_func: str | None = None


__all__ = ["SinglePurposeToolConfig", "SinglePurposeToolRisk"]