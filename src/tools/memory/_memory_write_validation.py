"""行动验证逻辑

Wiki 知识落地 P2 (GenericAgent): 行动验证原则

核心理念：No Execution, No Memory
只有经过成功工具调用的结果才能写入 L1/L2/L3。
"""

from ._memory_write_types import (
    VerifiedSource,
    ValidationResult,
    ALLOWED_SOURCES_FOR_L1L2L3,
    DENIED_SOURCES_FOR_L1L2L3,
)


def _validate_source(source: str | VerifiedSource | None, level: str) -> ValidationResult:
    """验证信息来源是否符合行动验证原则

    Args:
        source: 信息来源（字符串或 VerifiedSource）
        level: 目标层级（L1/L2/L3/L4）

    Returns:
        ValidationResult: 验证结果
    """
    # L4 允许所有来源（原始记录层）
    if level == "L4":
        return ValidationResult(allowed=True, reason="L4 allows all sources")

    # 解析 source
    if source is None:
        return ValidationResult(
            allowed=False,
            reason="Source must be specified for L1/L2/L3 writes",
            fallback_level="L4",
        )

    if isinstance(source, str):
        try:
            source = VerifiedSource(source.lower())
        except ValueError:
            return ValidationResult(
                allowed=False,
                reason=f"Unknown source type: {source}",
                fallback_level="L4",
            )

    # 检查是否在允许列表
    if source in ALLOWED_SOURCES_FOR_L1L2L3:
        return ValidationResult(allowed=True, reason=f"Source {source.value} is verified")

    # 禁止的来源
    if source in DENIED_SOURCES_FOR_L1L2L3:
        return ValidationResult(
            allowed=False,
            reason=f"Source {source.value} is not verified (No Execution, No Memory)",
            fallback_level="L4",
        )

    # 未知的来源类型
    return ValidationResult(
        allowed=False,
        reason=f"Source {source.value} is not in allowed list",
        fallback_level="L4",
    )


__all__ = ["_validate_source"]