"""
路径解析器 - Path Resolver

提供路径解析功能，含路径遍历防护。
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger("seed_agent.path")


def resolve_path(
    path: str,
    validate_safety,
    is_path_in_allowed_dirs,
    default_work_dir: Path,
    default_work_dir_resolved: str,
    project_root: Path,
    project_root_resolved: str,
) -> str:
    """解析路径，相对路径默认从 .seed 目录解析（含路径遍历防护）

    Args:
        path: 原始路径字符串
        validate_safety: 路径安全验证函数
        is_path_in_allowed_dirs: 检查路径是否在允许目录内的函数
        default_work_dir: 默认工作目录
        default_work_dir_resolved: 已解析的默认工作目录字符串
        project_root: 项目根目录
        project_root_resolved: 已解析的项目根目录字符串

    Returns:
        解析后的绝对路径

    Raises:
        ValueError: 路径不安全或超出允许范围
    """
    # 先展开 ~ 为用户主目录
    if path.startswith("~"):
        path = os.path.expanduser(path)

    # 安全验证
    is_safe, error = validate_safety(path)
    if not is_safe:
        raise ValueError(error)

    if os.path.isabs(path):
        return path

    # 相对路径：优先从 .seed 目录解析
    seed_path = default_work_dir / path
    try:
        resolved_seed = str(seed_path.resolve())
        if (
            resolved_seed.startswith((default_work_dir_resolved, project_root_resolved))
        ) and seed_path.exists():
            return resolved_seed
    except Exception as e:
        logger.debug(f"Failed to resolve seed path '{path}': {e}")

    # 再从项目根目录解析
    project_path = project_root / path
    try:
        resolved_project = str(project_path.resolve())
        if resolved_project.startswith(project_root_resolved) and project_path.exists():
            return resolved_project
    except Exception as e:
        logger.debug(f"Failed to resolve project path '{path}': {e}")

    # 如果都不存在，使用 .seed 目录作为默认目标
    final_path = str(default_work_dir / path)
    final_resolved = str(Path(final_path).resolve())
    if not final_resolved.startswith(default_work_dir_resolved):
        raise ValueError(f"Resolved path escapes allowed directories: {final_path}")

    return final_path


__all__ = ["resolve_path"]