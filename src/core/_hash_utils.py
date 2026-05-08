"""
哈希计算和文件扫描工具

基于 Claude Context FileSynchronizer 设计的辅助函数：
- 文件哈希生成（SHA-256）
- 忽略模式检查
- 目录扫描与哈希生成
"""

import hashlib
import logging
import os
from pathlib import Path

logger = logging.getLogger("seed_agent")


def hash_file(file_path: Path) -> str:
    """计算文件 SHA-256 哈希

    Args:
        file_path: 文件路径

    Returns:
        SHA-256 哈希字符串，失败时返回空字符串
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
    except (OSError, UnicodeDecodeError) as e:
        logger.warning(f"Failed to hash file {file_path}: {e}")
        return ""


def should_ignore(relative_path: str, ignore_patterns: list[str]) -> bool:
    """检查路径是否应被忽略

    Args:
        relative_path: 相对路径
        ignore_patterns: 忽略模式列表

    Returns:
        是否应忽略
    """
    # 隐藏文件/目录
    parts = relative_path.split(os.sep)
    if any(part.startswith(".") for part in parts):
        return True

    # 模式匹配
    for pattern in ignore_patterns:
        if pattern in parts:
            return True

    return False


def generate_file_hashes(
    root_dir: Path,
    supported_extensions: list[str],
    ignore_patterns: list[str],
) -> dict[str, str]:
    """递归扫描目录生成文件哈希

    Args:
        root_dir: 根目录
        supported_extensions: 支持的文件扩展名
        ignore_patterns: 忽略模式

    Returns:
        文件路径 -> 哈希值的映射
    """
    file_hashes: dict[str, str] = {}

    for root, dirs, files in os.walk(root_dir):
        # 过滤目录
        dirs[:] = [d for d in dirs if not should_ignore(d, ignore_patterns)]

        for file_name in files:
            file_path = Path(root) / file_name
            relative_path = str(file_path.relative_to(root_dir))

            # 检查扩展名
            ext = file_path.suffix
            if ext not in supported_extensions:
                continue

            # 检查忽略模式
            if should_ignore(relative_path, ignore_patterns):
                continue

            # 计算哈希
            hash_value = hash_file(file_path)
            if hash_value:
                file_hashes[relative_path] = hash_value

    return file_hashes


__all__ = [
    "hash_file",
    "should_ignore",
    "generate_file_hashes",
]