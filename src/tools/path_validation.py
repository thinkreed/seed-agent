"""路径验证工具 - 防止路径遍历攻击，确保文件操作安全

核心功能:
- validate_path_safety: 验证路径安全性
- resolve_path: 解析相对/绝对路径
- is_path_in_allowed_dirs: 检查路径是否在允许目录内
"""

import functools
import logging
import os
from pathlib import Path

from src.tools._path_resolver import resolve_path as _resolve_path_impl
from src.tools._validation_patterns import (
    detect_double_dot_traversal,
    detect_url_encoded_traversal,
    detect_utf8_overlong,
    validate_windows_path,
)

logger = logging.getLogger("seed_agent.path")

# 加载配置
try:
    from src.shared_config import get_path_validation_config
    _cfg = get_path_validation_config()
    PROJECT_ROOT = _cfg.project_root
    DEFAULT_WORK_DIR = _cfg.default_work_dir
    ALLOWED_DIRS_RAW = _cfg.allowed_dirs
except ImportError:
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    DEFAULT_WORK_DIR = Path.home() / ".seed"
    ALLOWED_DIRS_RAW = [DEFAULT_WORK_DIR, PROJECT_ROOT, Path.home() / "Documents"]


def _resolve_allowed_dirs() -> list[str]:
    resolved = []
    for allowed in ALLOWED_DIRS_RAW:
        try:
            resolved.append(str(Path(str(allowed)).resolve()))
        except Exception as e:
            logger.debug(f"Failed to resolve allowed dir '{allowed}': {e}")
    return resolved


ALLOWED_DIRS: list[str] = _resolve_allowed_dirs()
DEFAULT_WORK_DIR_RESOLVED = str(DEFAULT_WORK_DIR.resolve())
PROJECT_ROOT_RESOLVED = str(PROJECT_ROOT.resolve())


@functools.lru_cache(maxsize=1024)
def is_path_in_allowed_dirs(resolved_path: str) -> bool:
    """检查路径是否在允许目录内（使用缓存）"""
    return any(resolved_path.startswith(allowed) for allowed in ALLOWED_DIRS)


def validate_path_safety(path: str) -> tuple[bool, str]:
    """验证路径安全性，防止路径遍历攻击

    Args:
        path: 原始路径字符串

    Returns:
        (is_safe, error_message): 安全返回 (True, ""), 不安全返回 (False, 错误信息)
    """
    # 1. URL 编码绕过检测
    is_blocked, error = detect_url_encoded_traversal(path)
    if is_blocked:
        logger.warning(f"URL-encoded path traversal attempt blocked: {path}")
        return False, error

    # 2. UTF-8 过长编码检测
    is_blocked, error = detect_utf8_overlong(path)
    if is_blocked:
        logger.warning(f"UTF-8 overlong encoding detected: {path}")
        return False, error

    # 3. 双点序列检测
    is_blocked, error = detect_double_dot_traversal(path)
    if is_blocked:
        logger.warning(f"Path traversal attempt blocked: {path}")
        return False, error

    # 4. Windows 特殊路径检测
    if os.name == "nt":
        is_safe, error, was_handled = validate_windows_path(path, is_path_in_allowed_dirs)
        if was_handled:
            if not is_safe:
                logger.warning(f"Windows path validation failed: {path}")
            return is_safe, error

    # 5. 检查绝对路径是否在允许范围内
    if os.path.isabs(path):
        try:
            resolved = str(Path(path).resolve())
            if is_path_in_allowed_dirs(resolved):
                return True, ""
        except Exception as e:
            logger.debug(f"Failed to resolve absolute path '{path}': {e}")
        logger.warning(f"Absolute path outside allowed dirs: {path}")
        return False, f"Absolute path '{path}' is outside allowed directories"

    return True, ""


def resolve_path(path: str) -> str:
    """解析路径，相对路径默认从 .seed 目录解析（含路径遍历防护）

    Args:
        path: 原始路径字符串

    Returns:
        解析后的绝对路径

    Raises:
        ValueError: 路径不安全或超出允许范围
    """
    return _resolve_path_impl(
        path=path,
        validate_safety=validate_path_safety,
        is_path_in_allowed_dirs=is_path_in_allowed_dirs,
        default_work_dir=DEFAULT_WORK_DIR,
        default_work_dir_resolved=DEFAULT_WORK_DIR_RESOLVED,
        project_root=PROJECT_ROOT,
        project_root_resolved=PROJECT_ROOT_RESOLVED,
    )


__all__ = [
    "ALLOWED_DIRS",
    "DEFAULT_WORK_DIR",
    "PROJECT_ROOT",
    "is_path_in_allowed_dirs",
    "resolve_path",
    "validate_path_safety",
]