"""
L1-L4 记忆写入核心逻辑

基于 GenericAgent "行动验证原则" 设计：
- 只有经过成功工具调用的结果才能写入 L1/L2/L3
- L1 索引 ≤200 字符，仅导航信息
- L2 Skill 必须符合 Open Agent Skills 规范 (YAML frontmatter)
- L3 Knowledge 存储跨任务模式和原则
- L4 Raw 存储原始会话数据

核心功能：
- write_memory: 标准化记忆写入接口
- _validate_skill_format: L2 Skill 格式验证
- _get_path: 记忆路径映射
"""

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)


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


def write_memory(level: str, content: str, title: str = "", metadata: str = "") -> str:
    """
    Write memory to L1/L2/L3/L4. Validates content length and structure.

    核心约束：
    - L1 索引 ≤200 字符，无代码块/子章节
    - L2 Skill 必须符合 Open Agent Skills 规范
    - L3/L4 带标题格式写入

    Args:
        level: L1 (Index), L2 (Skill), L3 (Knowledge), L4 (Raw)
        content: Memory content (for L2, must be SKILL.md format with YAML frontmatter)
        title: Memory title or skill name (for L2-L4). For L1, it's the section header.
        metadata: Optional metadata (source, date, etc.)

    Returns:
        Success message or error description
    """
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

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)

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
                f.write(content.strip() + "\n")
        else:
            with open(path, "w", encoding="utf-8") as f:
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