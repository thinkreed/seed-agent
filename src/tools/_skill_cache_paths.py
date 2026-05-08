"""
磁盘快照缓存 - 路径管理与 Manifest 构建

提供缓存目录路径获取和技能目录变更检测功能。
"""

import hashlib
import json
from pathlib import Path


def get_cache_dir() -> Path:
    """获取缓存目录（动态）"""
    try:
        from src.shared_config import get_paths_config

        return get_paths_config().cache_dir
    except RuntimeError:
        return Path.home() / ".seed" / "cache"


def get_snapshot_path() -> Path:
    """获取快照文件路径"""
    return get_cache_dir() / "skills_snapshot.json"


# 缓存路径缓存（延迟初始化）
_CACHE_DIR: Path | None = None
_SNAPSHOT_PATH: Path | None = None
SNAPSHOT_PATH: Path | None = None  # 向后兼容别名


def ensure_cache_paths() -> tuple[Path, Path]:
    """确保缓存路径已初始化（带缓存）

    Returns:
        (cache_dir, snapshot_path) 元组
    """
    global _CACHE_DIR, _SNAPSHOT_PATH, SNAPSHOT_PATH
    if _CACHE_DIR is None:
        _CACHE_DIR = get_cache_dir()
        _SNAPSHOT_PATH = get_snapshot_path()
        SNAPSHOT_PATH = _SNAPSHOT_PATH  # 向后兼容
    return _CACHE_DIR, _SNAPSHOT_PATH


def build_manifest(skills_dir: Path) -> str:
    """
    构建技能目录的 manifest (mtime + size) 用于缓存失效检测

    Args:
        skills_dir: 技能目录路径

    Returns:
        SHA256 hash 字符串，空目录返回空字符串
    """
    if not skills_dir.exists():
        return ""

    manifest = {}
    for skill_dir in sorted(skills_dir.iterdir()):
        if skill_dir.is_dir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                stat = skill_file.stat()
                manifest[str(skill_dir.name)] = {
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                }

    # 使用 sha256 生成 manifest hash
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


__all__ = [
    "get_cache_dir",
    "get_snapshot_path",
    "ensure_cache_paths",
    "build_manifest",
    "SNAPSHOT_PATH",
]