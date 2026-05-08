"""路径安全验证 - 基于qwen-code DeclarativeTool权限体系：三级权限、路径遍历防护、编码绕过检测"""

import functools
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("seed_agent.path")

# 配置加载
try:
    from src.shared_config import get_path_validation_config
    _path_config = get_path_validation_config()
    PROJECT_ROOT, DEFAULT_WORK_DIR = _path_config.project_root, _path_config.default_work_dir
    ALLOWED_DIRS_RAW = _path_config.allowed_dirs
except ImportError:
    PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
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

# 预编译正则
_RE_WINDOWS_DRIVE = re.compile(r"^[a-zA-Z]:[/\\]")
_RE_DOUBLE_DOT = re.compile(r"\.\.")
_RE_URL_ENCODED = re.compile(r"%[0-9a-fA-F]{2}", re.IGNORECASE)
_RE_DOUBLE_URL_ENCODED = re.compile(r"%25[0-9a-fA-F]{2}", re.IGNORECASE)
_RE_UTF8_OVERLONG = re.compile(r"[\xc0-\xc1][\x80-\xbf]|\xe0\x80[\xae\xaf]|\xed\xa0[\x80-\xbf]")

@functools.lru_cache(maxsize=1024)
def _is_path_in_allowed_dirs(resolved_path: str) -> bool:
    """检查路径是否在允许目录内（缓存）"""
    return any(resolved_path.startswith(allowed) for allowed in ALLOWED_DIRS)

def _validate_path_safety(path: str) -> tuple[bool, str]:
    """验证路径安全性，防止路径遍历攻击。返回(is_safe, error_message)"""
    # URL编码绕过检测
    path_lower = path.lower()
    if _RE_URL_ENCODED.search(path_lower) or _RE_DOUBLE_URL_ENCODED.search(path_lower):
        try:
            from urllib.parse import unquote
            decoded_once, decoded_twice = unquote(path), unquote(unquote(path))
            for decoded in [path, decoded_once, decoded_twice]:
                if ".." in decoded or decoded.startswith(("/", "\\")):
                    logger.warning(f"URL-encoded path traversal blocked: {path}")
                    return False, f"URL-encoded path blocked: '{path[:50]}...'"
        except Exception:
            return False, f"URL-encoded path blocked: '{path[:50]}...'"

    # UTF-8过长编码检测
    if _RE_UTF8_OVERLONG.search(path):
        logger.warning(f"UTF-8 overlong encoding detected: {path}")
        return False, f"UTF-8 overlong encoding blocked: '{path[:50]}...'"

    # 路径遍历检测
    if _RE_DOUBLE_DOT.search(path):
        normalized = path.replace("\\", "/")
        depth = sum(-1 if p == ".." else (1 if p and p != "." else 0) for p in normalized.split("/"))
        if depth < 0:
            logger.warning(f"Path traversal attempt blocked: {path}")
            return False, f"Path traversal blocked: '{path}'"

    # Windows特殊攻击
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

    # 绝对路径检查
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
    """解析路径，相对路径默认从.seed目录解析。Raises: ValueError: 路径不安全"""
    if path.startswith("~"):
        path = os.path.expanduser(path)

    is_safe, error = _validate_path_safety(path)
    if not is_safe:
        raise ValueError(error)

    if os.path.isabs(path):
        return path

    # 相对路径：优先.seed目录
    seed_path = DEFAULT_WORK_DIR / path
    try:
        resolved_seed = str(seed_path.resolve())
        if resolved_seed.startswith(DEFAULT_WORK_DIR_RESOLVED) and seed_path.exists():
            return resolved_seed
    except Exception:
        pass

    # 再从项目根目录
    project_path = PROJECT_ROOT / path
    try:
        resolved_project = str(project_path.resolve())
        if resolved_project.startswith(PROJECT_ROOT_RESOLVED) and project_path.exists():
            return resolved_project
    except Exception:
        pass

    # 默认.seed目录
    final_resolved = str((DEFAULT_WORK_DIR / path).resolve())
    if not final_resolved.startswith(DEFAULT_WORK_DIR_RESOLVED):
        raise ValueError(f"Resolved path escapes allowed directories: {final_resolved}")
    return final_resolved