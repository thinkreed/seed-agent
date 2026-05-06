"""
L1-L4 记忆写入核心逻辑

基于 GenericAgent "行动验证原则" 设计：
- 只有经过成功工具调用的结果才能写入 L1/L2/L3
- L1 索引 ≤200 字符，仅导航信息
- L2 Skill 必须符合 Open Agent Skills 规范 (YAML frontmatter)
- L3 Knowledge 存储跨任务模式和原则
- L4 Raw 存储原始会话数据

基于 MIA "记忆去重阈值" 设计：
- 相似度 ≥ 0.9999 时执行去重逻辑
- 现有记忆错误 + 新记忆正确 → 替换
- 都正确 → 保留更短版本

核心功能：
- write_memory: 标准化记忆写入接口（行动验证 + 去重）
- _validate_skill_format: L2 Skill 格式验证
- _validate_source: 行动验证原则校验
- _check_similarity: 记忆去重检查
- _get_path: 记忆路径映射
"""

import logging
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================================
# Wiki 知识落地 P2: 行动验证原则 (GenericAgent)
# ============================================================================


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


# ============================================================================
# Wiki 知识落地 P2: 记忆去重阈值 (MIA)
# ============================================================================

DEDUPLICATION_THRESHOLD = 0.9999  # 相似度阈值


def _compute_similarity(text1: str, text2: str) -> float:
    """计算文本相似度（简化版 TF-IDF 余弦相似度）

    Args:
        text1: 文本1
        text2: 文本2

    Returns:
        相似度分数 [0.0, 1.0]
    """
    if not text1 or not text2:
        return 0.0

    # 简化的关键词提取（词频统计）
    words1 = text1.lower().split()
    words2 = text2.lower().split()

    # 去除常见停用词
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                 "have", "has", "had", "do", "does", "did", "will", "would", "could",
                 "should", "may", "might", "must", "shall", "can", "need", "dare",
                 "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by",
                 "from", "as", "into", "through", "during", "before", "after",
                 "above", "below", "between", "under", "again", "further", "then",
                 "once", "here", "there", "when", "where", "why", "how", "all", "each",
                 "few", "more", "most", "other", "some", "such", "no", "nor", "not",
                 "only", "own", "same", "so", "than", "too", "very", "just", "and",
                 "but", "if", "or", "because", "until", "while", "although", "though",
                 "的", "是", "在", "有", "和", "与", "或", "但", "如果", "因为", "所以",
                 "这", "那", "一个", "这个", "那个", "之", "了", "着", "过"}

    words1 = [w for w in words1 if w not in stopwords and len(w) > 1]
    words2 = [w for w in words2 if w not in stopwords and len(w) > 1]

    if not words1 or not words2:
        return 0.0

    # 计算词频
    freq1 = {}
    freq2 = {}
    for w in words1:
        freq1[w] = freq1.get(w, 0) + 1
    for w in words2:
        freq2[w] = freq2.get(w, 0) + 1

    # 计算交集和余弦相似度
    intersection = set(freq1.keys()) & set(freq2.keys())
    if not intersection:
        return 0.0

    dot_product = sum(freq1[w] * freq2[w] for w in intersection)
    norm1 = sum(v ** 2 for v in freq1.values()) ** 0.5
    norm2 = sum(v ** 2 for v in freq2.values()) ** 0.5

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


def _check_existing_memory(path: str, content: str, metadata: str = "") -> str | None:
    """检查是否存在相似记忆，返回去重决策

    MIA 记忆去重逻辑：
    - 相似度 ≥ 0.9999 时执行去重
    - 现有记忆错误 + 新记忆正确 → 替换
    - 都正确 → 保留更短版本
    - 无相似记忆 → 允许写入

    Args:
        path: 目标路径
        content: 新内容
        metadata: 元数据（包含验证状态）

    Returns:
        None: 允许写入
        str: 去重决策消息（阻止写入或建议替换）
    """
    if not os.path.exists(path):
        return None  # 文件不存在，允许写入

    try:
        with open(path, encoding="utf-8") as f:
            existing_content = f.read()
    except Exception:
        return None  # 无法读取，允许写入

    # 计算相似度
    similarity = _compute_similarity(existing_content, content)

    if similarity < DEDUPLICATION_THRESHOLD:
        return None  # 相似度低于阈值，允许写入

    # 检查验证状态（从 metadata 提取）
    existing_verified = "verified=true" in existing_content.lower() or "tool_call_success" in existing_content
    new_verified = "verified=true" in metadata.lower() or metadata == ""

    # MIA 去重逻辑
    if not existing_verified and new_verified:
        # 现有记忆错误，新记忆正确 → 替换
        return f"REPLACE: Existing memory has lower verification (similarity={similarity:.4f})"

    if existing_verified and new_verified:
        # 都正确 → 保留更短版本
        existing_len = len(existing_content.strip())
        new_len = len(content.strip())
        if new_len < existing_len:
            return f"REPLACE: New content is shorter (similarity={similarity:.4f})"
        else:
            return f"SKIP: Existing content is shorter/better (similarity={similarity:.4f})"

    # 现有记忆正确，新记忆未验证 → 保留现有
    return f"SKIP: Existing memory is verified, new is not (similarity={similarity:.4f})"


def _get_memory_root() -> Path:
    """获取记忆根目录（动态）"""
    try:
        from src.shared_config import get_paths_config
        return get_paths_config().memory_dir
    except RuntimeError:
        # PathsConfig 未初始化时使用 fallback
        return Path.home() / ".seed" / "memory"


def _get_sessions_dir() -> Path:
    """获取会话目录"""
    return _get_memory_root() / "raw" / "sessions"


def _validate_skill_format(content: str, name: str = "") -> str:
    """校验 L2 Skill 格式是否符合 Open Agent Skills 规范

    Args:
        content: Skill 内容 (包含 YAML frontmatter)
        name: Skill 名称/文件名

    Returns:
        错误信息字符串，空字符串表示校验通过
    """
    # 校验 YAML frontmatter
    if not content.strip().startswith("---"):
        return "Error: L2 Skill must start with YAML frontmatter (---)."

    # 提取 frontmatter
    parts = content.split("---", 2)
    if len(parts) < 3:
        return "Error: L2 Skill must have closing --- for frontmatter."

    frontmatter_text = parts[1].strip()

    # 校验必需字段
    required_fields = ["name", "description"]
    for field in required_fields:
        if field not in frontmatter_text:
            return f"Error: L2 Skill frontmatter must contain '{field}' field."

    # 解析 name 字段
    name_match = re.search(r'name:\s*["\']?([^"\':\n]+)["\']?', frontmatter_text)
    if name_match:
        skill_name = name_match.group(1).strip()
        # name 校验规则：小写字母/数字/连字符，1-64字符
        if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", skill_name):
            return (
                f"Error: L2 Skill name '{skill_name}' must be lowercase "
                f"letters/numbers/hyphens, 1-64 chars, "
                f"no leading/trailing/consecutive hyphens."
            )
        if len(skill_name) > 64:
            return "Error: L2 Skill name exceeds 64 chars limit."

    # 校验 description 长度
    desc_match = re.search(
        r'description:\s*["\']?(.+?)["\']?\n', frontmatter_text, re.DOTALL
    )
    if desc_match:
        desc = desc_match.group(1).strip()
        if len(desc) > 1024:
            return "Error: L2 Skill description exceeds 1024 chars limit."
        if not desc:
            return "Error: L2 Skill description cannot be empty."

    # 校验文件名：必须是 skill_name/SKILL.md 格式
    if name:
        expected_name = f"{skill_name}/SKILL.md"
        if name not in (expected_name, "SKILL.md"):
            return f"Error: L2 filename must be '{expected_name}' (skill directory with SKILL.md)."

    return ""  # 校验通过


def _get_path(level: str, filename: str | None = None) -> str | None:
    """获取记忆文件路径

    Args:
        level: L1/L2/L3/L4
        filename: 文件名（L2-L4 需要）

    Returns:
        完整路径字符串，None 表示参数错误
    """
    mapping = {"L1": "notes.md", "L2": "skills", "L3": "knowledge", "L4": "raw"}
    if level not in mapping:
        return None
    base = mapping[level]
    memory_root = _get_memory_root()

    # L1 是单个文件，无需 filename
    if level == "L1":
        return os.path.join(memory_root, base)

    # L2-L4 需要指定 filename
    if not filename:
        return None

    # L2 特殊处理：skill 目录结构，自动补全 SKILL.md
    if level == "L2" and not filename.endswith("/SKILL.md") and filename != "SKILL.md":
        filename = os.path.join(filename, "SKILL.md")

    return os.path.join(memory_root, base, filename)


def write_memory(
    level: str,
    content: str,
    title: str = "",
    metadata: str = "",
    source: str | VerifiedSource | None = None,
) -> str:
    """
    Write memory to L1/L2/L3/L4. Validates content length, structure, source, and deduplication.

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
        content: Memory content (for L2, must be SKILL.md format with YAML frontmatter)
        title: Memory title or skill name (for L2-L4). For L1, it's the section header.
        metadata: Optional metadata (source, date, etc.)
        source: Information source (Wiki P2: Action Verification Principle)
                - tool_call_success: 来自成功的工具调用
                - external_verification: 外部验证（用户确认）
                - read_from_file: 从文件读取
                - system_init: 系统初始化
                - model_inference: 模型推理（禁止 L1/L2/L3）
                - planning: 未执行计划（禁止 L1/L2/L3）
                - unverified: 未验证信息（禁止 L1/L2/L3）

    Returns:
        Success message or error description
    """
    # Wiki P2: 行动验证原则
    validation_result = _validate_source(source, level)
    if not validation_result.allowed:
        # 验证失败，建议降级到 L4
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
            # 相似度高，保留现有记忆
            logger.info(f"Memory deduplication: {dedup_result}")
            return f"Skipped: {dedup_result}"
        elif dedup_result.startswith("REPLACE:"):
            # 相似度高，替换现有记忆
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
            # L2 写入 SKILL.md 格式（content 应已包含 frontmatter）
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
        logger.exception(f"Unexpected error writing memory to {path}: {type(e).__name__}")
        return f"Error writing memory: {type(e).__name__}: {str(e)[:100]}"