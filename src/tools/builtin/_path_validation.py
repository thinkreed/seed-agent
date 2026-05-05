"""
路径安全验证

基于 qwen-code DeclarativeTool 权限体系设计：
- 三级权限模式: allow / ask / deny
- 路径遍历防护
- URL 编码绕过检测
- UTF-8 过长编码检测

核心功能：
- _validate_path_safety: 验证路径安全性
- _resolve_path: 路径解析和展开
- _is_path_in_allowed_dirs: 检查路径是否在允许目录内
"""

import functools
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("seed_agent.path")

# 使用共享配置模块
try:
    from src.shared_config import get_path_validation_config

    _path_config = get_path_validation_config()
    PROJECT_ROOT = _path_config.project_root
    DEFAULT_WORK_DIR = _path_config.default_work_dir
    ALLOWED_DIRS_RAW = _path_config.allowed_dirs
except ImportError:
    # Fallback: 使用默认值
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
    DEFAULT_WORK_DIR = Path.home() / ".seed"
    ALLOWED_DIRS_RAW = [
        DEFAULT_WORK_DIR,
        PROJECT_ROOT,
        Path.home() / "Documents",
    ]


def _resolve_allowed_dirs() -> list[str]:
    """解析并缓存 ALLOWED_DIRS"""
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


# 预编译正则表达式（性能优化）
_RE_WINDOWS_DRIVE = re.compile(r"^[a-zA-Z]:[/\\]")
_RE_DOUBLE_DOT = re.compile(r"\.\.")

# URL 编码攻击模式
_RE_URL_ENCODED = re.compile(r"%[0-9a-fA-F]{2}", re.IGNORECASE)
_RE_DOUBLE_URL_ENCODED = re.compile(r"%25[0-9a-fA-F]{2}", re.IGNORECASE)
_RE_UTF8_OVERLONG = re.compile(
    r"[\xc0-\xc1][\x80-\xbf]|\xe0\x80[\xae\xaf]|\xed\xa0[\x80-\xbf]"
)


@functools.lru_cache(maxsize=1024)
def _is_path_in_allowed_dirs(resolved_path: str) -> bool:
    """检查路径是否在允许目录内（使用缓存）"""
    return any(resolved_path.startswith(allowed) for allowed in ALLOWED_DIRS)


def _validate_path_safety(path: str) -> tuple[bool, str]:
    """
    验证路径安全性，防止路径遍历攻击。

    Args:
        path: 原始路径字符串

    Returns:
        (is_safe, error_message): 安全返回 (True, ""), 不安全返回 (False, 错误信息)
    """
    # 1. URL 编码绕过检测
    path_lower = path.lower()
    if _RE_URL_ENCODED.search(path_lower) or _RE_DOUBLE_URL_ENCODED.search(path_lower):
        try:
            from urllib.parse import unquote

            decoded_once = unquote(path)
            decoded_twice = unquote(decoded_once)
            for decoded in [path, decoded_once, decoded_twice]:
                if ".." in decoded or decoded.startswith(("/", "\\")):
                    logger.warning(f"URL-encoded path traversal blocked: {path}")
                    return (
                        False,
                        f"URL-encoded path blocked: '{path[:50]}...'",
                    )
        except Exception:
            return False, f"URL-encoded path blocked: '{path[:50]}...'"

    # 2. UTF-8 过长编码检测
    if _RE_UTF8_OVERLONG.search(path):
        logger.warning(f"UTF-8 overlong encoding detected: {path}")
        return False, f"UTF-8 overlong encoding blocked: '{path[:50]}...'"

    # 3. 快速检测 .. 序列
    if _RE_DOUBLE_DOT.search(path):
        normalized = path.replace("\\", "/")
        parts = normalized.split("/")
        depth = 0
        for part in parts:
            if part == "..":
                depth -= 1
            elif part and part != ".":
                depth += 1
        if depth < 0:
            logger.warning(f"Path traversal attempt blocked: {path}")
            return False, f"Path traversal blocked: '{path}'"

    # Windows 特殊攻击模式
    if os.name == "nt":
        if _RE_WINDOWS_DRIVE.match(path):
            try:
                resolved = str(Path(path).resolve())
                if _is_path_in_allowed_dirs(resolved):
                    return True, ""
            except Exception:
                pass
            return False, f"Windows drive path '{path}' is outside allowed directories"

        if path.startswith(("\\\\", "//")):
            return False, f"UNC path '{path}' is not allowed"

    # 检查绝对路径
    if os.path.isabs(path):
        try:
            resolved = str(Path(path).resolve())
            if _is_path_in_allowed_dirs(resolved):
                return True, ""
        except Exception:
            pass
        return False, f"Absolute path '{path}' is outside allowed directories"

    return True, ""


def _resolve_path(path: str) -> str:
    """解析路径，相对路径默认从 .seed 目录解析

    Args:
        path: 原始路径

    Returns:
        解析后的绝对路径

    Raises:
        ValueError: 路径不安全或超出允许范围
    """
    # 先展开 ~ 为用户主目录
    if path.startswith("~"):
        path = os.path.expanduser(path)

    # 安全验证
    is_safe, error = _validate_path_safety(path)
    if not is_safe:
        raise ValueError(error)

    if os.path.isabs(path):
        return path

    # 相对路径：优先从 .seed 目录解析
    seed_path = DEFAULT_WORK_DIR / path
    try:
        resolved_seed = str(seed_path.resolve())
        if resolved_seed.startswith(DEFAULT_WORK_DIR_RESOLVED) and seed_path.exists():
            return resolved_seed
    except Exception:
        pass

    # 再从项目根目录解析
    project_path = PROJECT_ROOT / path
    try:
        resolved_project = str(project_path.resolve())
        if resolved_project.startswith(PROJECT_ROOT_RESOLVED) and project_path.exists():
            return resolved_project
    except Exception:
        pass

    # 默认使用 .seed 目录
    final_path = str(DEFAULT_WORK_DIR / path)
    final_resolved = str(Path(final_path).resolve())
    if not final_resolved.startswith(DEFAULT_WORK_DIR_RESOLVED):
        raise ValueError(f"Resolved path escapes allowed directories: {final_path}")

    return final_resolved