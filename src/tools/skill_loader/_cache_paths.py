"""
缓存路径管理模块

路径从 PathsConfig 动态获取，支持 fallback 机制。
"""

from pathlib import Path


def get_cache_dir() -> Path:
    """获取缓存目录（动态）"""
    try:
        from src.shared_config import get_paths_config

        return get_paths_config().cache_dir
    except RuntimeError:
        # PathsConfig 未初始化时使用 fallback
        return Path.home() / ".seed" / "cache"


def get_snapshot_file_path() -> Path:
    """获取快照文件路径"""
    return get_cache_dir() / "skills_snapshot.json"


# 缓存路径配置（延迟获取）
CACHE_DIR = None  # 类型: Path | None
SNAPSHOT_PATH = None  # 类型: Path | None


def ensure_cache_paths() -> tuple[Path, Path]:
    """确保缓存路径已初始化"""
    global CACHE_DIR, SNAPSHOT_PATH
    if CACHE_DIR is None:
        CACHE_DIR = get_cache_dir()
        SNAPSHOT_PATH = get_snapshot_file_path()
    return CACHE_DIR, SNAPSHOT_PATH


def get_snapshot_path() -> Path:
    """获取快照路径（动态）"""
    ensure_cache_paths()
    return SNAPSHOT_PATH or get_snapshot_file_path()


__all__ = [
    "CACHE_DIR",
    "SNAPSHOT_PATH",
    "ensure_cache_paths",
    "get_cache_dir",
    "get_snapshot_file_path",
    "get_snapshot_path",
]