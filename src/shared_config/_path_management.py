"""路径管理模块

提供全局 PathsConfig 访问接口和便利函数。

内容:
- init_paths_config - 初始化全局路径配置
- get_paths_config - 获取全局路径配置
- 便利访问函数 (get_seed_dir, get_memory_dir 等)
- 带 Fallback 的路径函数
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.models import PathsConfig

# 全局 PathsConfig 实例（延迟初始化）
_paths_config: Optional["PathsConfig"] = None


def init_paths_config(config: "PathsConfig") -> None:
    """初始化全局路径配置

    Args:
        config: PathsConfig 实例

    Raises:
        RuntimeError: 重复初始化
    """
    global _paths_config
    if _paths_config is not None:
        raise RuntimeError("PathsConfig 已经初始化，不可重复调用")
    _paths_config = config


def get_paths_config() -> "PathsConfig":
    """获取全局路径配置

    Returns:
        PathsConfig: 路径配置实例

    Raises:
        RuntimeError: 未初始化
    """
    if _paths_config is None:
        raise RuntimeError(
            "PathsConfig 未初始化，请先调用 init_paths_config() "
            "或在 AgentLoop 启动后使用"
        )
    return _paths_config


# ========== 便利访问函数 ==========


def get_seed_dir() -> Path:
    """获取主工作目录"""
    return get_paths_config().seed_base


def get_memory_dir() -> Path:
    """获取记忆目录"""
    return get_paths_config().memory_dir


def get_logs_dir() -> Path:
    """获取日志目录"""
    return get_paths_config().logs_dir


def get_tasks_dir() -> Path:
    """获取任务目录"""
    return get_paths_config().tasks_dir


def get_cache_dir() -> Path:
    """获取缓存目录"""
    return get_paths_config().cache_dir


def get_sandbox_dir() -> Path:
    """获取沙盒目录"""
    return get_paths_config().sandbox_dir


def get_ralph_dir() -> Path:
    """获取 Ralph Loop 目录"""
    return get_paths_config().ralph_dir


def get_vault_dir() -> Path:
    """获取凭证存储目录"""
    return get_paths_config().vault_dir


def get_allowed_dirs() -> list[Path]:
    """获取允许访问的目录列表"""
    return get_paths_config().allowed_dirs_resolved


def get_project_root() -> Path:
    """获取项目根目录"""
    return get_paths_config().project_root


def get_wiki_dir() -> Path | None:
    """获取 Wiki 目录"""
    return get_paths_config().wiki_dir


# ========== 带 Fallback 的路径函数（用于初始化前场景） ==========


def get_seed_dir_with_fallback() -> Path:
    """获取主工作目录（带 fallback）

    用于 PathsConfig 未初始化时的场景（如模块导入时）
    """
    try:
        return get_paths_config().seed_base
    except RuntimeError:
        return Path.home() / ".seed"


def get_memory_dir_with_fallback() -> Path:
    """获取记忆目录（带 fallback）"""
    try:
        return get_paths_config().memory_dir
    except RuntimeError:
        return Path.home() / ".seed" / "memory"


def get_ralph_dir_with_fallback() -> Path:
    """获取 Ralph Loop 目录（带 fallback）"""
    try:
        return get_paths_config().ralph_dir
    except RuntimeError:
        return Path.home() / ".seed" / "ralph"


def get_tasks_dir_with_fallback() -> Path:
    """获取任务目录（带 fallback）"""
    try:
        return get_paths_config().tasks_dir
    except RuntimeError:
        return Path.home() / ".seed" / "tasks"


def get_cache_dir_with_fallback() -> Path:
    """获取缓存目录（带 fallback）"""
    try:
        return get_paths_config().cache_dir
    except RuntimeError:
        return Path.home() / ".seed" / "cache"


def get_sandbox_dir_with_fallback() -> Path:
    """获取沙盒目录（带 fallback）"""
    try:
        return get_paths_config().sandbox_dir
    except RuntimeError:
        return Path.home() / ".seed" / "sandbox"