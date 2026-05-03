"""
安全扫描模块 - Skill 内容和结构的安全验证

包含:
1. Prompt Injection 检测
2. 符号链接逃逸检测
3. 可疑二进制文件检测
"""

from pathlib import Path

# Prompt Injection 检测模式 (参考 Hermes skills_guard.py)
INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous",
    "you are now",
    "disregard your",
    "forget your instructions",
    "new instructions:",
    "system prompt:",
    "<system>",
    "]]>",
    "ignore all the instructions",
    "you must forget",
]

# 可疑二进制文件扩展名
SUSPICIOUS_EXTENSIONS = {".exe", ".dll", ".so", ".dylib", ".bin", ".dat", ".com"}


def scan_for_injections(content: str) -> str | None:
    """
    检测 Skill 内容中的 Prompt Injection 攻击

    Args:
        content: Skill 文件内容

    Returns:
        发现攻击时的警告消息，安全时返回 None
    """
    content_lower = content.lower()
    for pattern in INJECTION_PATTERNS:
        if pattern in content_lower:
            return f"Potential prompt injection detected: '{pattern}'"
    return None


def validate_skill_structure(skill_dir: Path) -> str | None:
    """
    验证 Skill 目录结构安全

    检查:
    - 符号链接逃逸（指向 skill 目录外的路径）
    - 可疑二进制文件

    Args:
        skill_dir: Skill 目录路径

    Returns:
        发现安全问题时的警告消息，安全时返回 None
    """
    try:
        skill_dir_resolved = skill_dir.resolve()

        # 单次遍历检查所有安全问题
        for item in skill_dir.rglob("*"):
            # 检查符号链接逃逸
            if item.is_symlink():
                resolved = item.resolve()
                if not str(resolved).startswith(str(skill_dir_resolved)):
                    return f"Symlink escape detected: {item} -> {resolved}"

            # 检查可疑二进制文件
            if item.is_file() and item.suffix.lower() in SUSPICIOUS_EXTENSIONS:
                return f"Suspicious binary file: {item}"

    except (OSError, PermissionError):
        pass

    return None


def validate_path_within_dir(target: Path, base_dir: Path) -> bool:
    """
    验证目标路径是否在基准目录内（防止路径穿越）

    Args:
        target: 待验证的目标路径
        base_dir: 基准目录

    Returns:
        True 表示路径安全，False 表示路径穿越
    """
    try:
        return str(target.resolve()).startswith(str(base_dir.resolve()))
    except (OSError, PermissionError):
        return False
