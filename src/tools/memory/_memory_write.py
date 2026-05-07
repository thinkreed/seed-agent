"""记忆写入入口模块 (Wiki 知识落地 P2)

模块拆分：
- _memory_write_types.py: 验证来源类型和结果
- _memory_write_validation.py: 行动验证逻辑
- _memory_write_dedup.py: 去重逻辑
- _memory_write_utils.py: 辅助函数（路径、格式校验）
- _memory_write.py: write_memory 主函数

基于 GenericAgent "行动验证原则" 和 MIA "记忆去重阈值" 设计。
"""

import logging
import os

from ._memory_write_dedup import _check_existing_memory
from ._memory_write_types import VerifiedSource
from ._memory_write_utils import _get_path, _validate_skill_format
from ._memory_write_validation import _validate_source

logger = logging.getLogger(__name__)


def write_memory(
    level: str,
    content: str,
    title: str = "",
    metadata: str = "",
    source: str | VerifiedSource | None = None,
) -> str:
    """
    Write memory to L1/L2/L3/L4.

    Wiki 知识落地 P2:
    - 行动验证原则 (GenericAgent): 只有成功的工具调用结果才能写入 L1/L2/L3
    - 记忆去重阈值 (MIA): 相似度 ≥ 0.9999 时执行去重逻辑

    核心约束：
    - L1 索引 ≤200 字符，无代码块/子章节
    - L2 Skill 必须符合 Open Agent Skills 规范
    - L3/L4 带标题格式写入
    - source 必须是允许的类型（L1/L2/L3）

    Args:
        level: L1 (Index), L2 (Skill), L3 (Knowledge), L4 (Raw)
        content: Memory content (for L2, must be SKILL.md format)
        title: Memory title or skill name (for L2-L4)
        metadata: Optional metadata (source, date, etc.)
        source: Information source (Wiki P2: Action Verification Principle)

    Returns:
        Success message or error description
    """
    # Wiki P2: 行动验证原则
    validation_result = _validate_source(source, level)
    if not validation_result.allowed:
        logger.warning(
            f"Memory write rejected: {validation_result.reason}. "
            f"Consider writing to {validation_result.fallback_level} instead."
        )
        return f"Error: {validation_result.reason}. Use {validation_result.fallback_level} for unverified content."

    # L1 校验：索引简短，无详细步骤
    if level == "L1":
        if len(content) > 200:
            return "Error: L1 content exceeds 200 chars (Index only)."
        if "##" in content or "```" in content:
            return "Error: L1 cannot contain subsections or code blocks."

    # L2 校验：必须符合 Open Agent Skills 规范
    if level == "L2":
        validation = _validate_skill_format(content, title)
        if validation:
            return validation

    path = _get_path(level, title)
    if not path:
        return "Error: Invalid level or missing filename."

    # Wiki P2: 记忆去重检查
    dedup_result = _check_existing_memory(path, content, metadata)
    if dedup_result:
        if dedup_result.startswith("SKIP:"):
            logger.info(f"Memory deduplication: {dedup_result}")
            return f"Skipped: {dedup_result}"
        elif dedup_result.startswith("REPLACE:"):
            logger.info(f"Memory deduplication: {dedup_result}")
            # 继续执行写入（替换）

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)

        # 构建带验证标记的内容
        verified_marker = ""
        if source and level in ("L2", "L3"):
            source_str = source.value if isinstance(source, VerifiedSource) else source
            verified_marker = f"<!-- verified=true, source={source_str} -->\n"

        if level == "L1":
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"\n## {title}\n")
                f.write(content.strip() + "\n")
            return f"Updated L1 Index: {title}"

        # L2 直接写入 content（已包含 YAML frontmatter）
        # L3/L4 写入带标题的格式
        if level == "L2":
            with open(path, "w", encoding="utf-8") as f:
                if verified_marker:
                    f.write(verified_marker)
                f.write(content.strip() + "\n")
        else:
            with open(path, "w", encoding="utf-8") as f:
                if verified_marker:
                    f.write(verified_marker)
                if metadata:
                    f.write(f"<!-- {metadata} -->\n")
                f.write(f"# {title}\n")
                f.write(content.strip() + "\n")

        return f"Saved {level} Memory: {os.path.basename(path)}"

    except PermissionError:
        return f"Error writing memory: Permission denied - {path}"
    except OSError as e:
        return f"Error writing memory: OS error - {type(e).__name__}: {str(e)[:100]}"
    except Exception as e:
        logger.exception(f"Unexpected error writing memory to {path}")
        return f"Error writing memory: {type(e).__name__}: {str(e)[:100]}"


# 导出所有公共接口
from ._memory_write_dedup import (
    DEDUPLICATION_THRESHOLD,
    _compute_similarity,
)
from ._memory_write_types import (
    ALLOWED_SOURCES_FOR_L1L2L3,
    DENIED_SOURCES_FOR_L1L2L3,
    ValidationResult,
    VerifiedSource,
)
from ._memory_write_utils import (
    _get_memory_root,
    _get_sessions_dir,
)

__all__ = [
    # 类型
    "VerifiedSource",
    "ValidationResult",
    "ALLOWED_SOURCES_FOR_L1L2L3",
    "DENIED_SOURCES_FOR_L1L2L3",
    # 常量
    "DEDUPLICATION_THRESHOLD",
    # 核心函数
    "write_memory",
    "_validate_source",
    "_compute_similarity",
    "_check_existing_memory",
    "_get_memory_root",
    "_get_sessions_dir",
    "_get_path",
    "_validate_skill_format",
]