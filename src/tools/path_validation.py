"""
路径验证工具 - Path Validation Utilities

防止路径遍历攻击，确保文件操作安全。

核心功能:
- validate_path_safety: 验证路径安全性
- resolve_path: 解析相对/绝对路径
- is_path_in_allowed_dirs: 检查路径是否在允许目录内

安全防护:
- 路径遍历检测（.. 序列）
- URL 编码绕过检测
- UTF-8 过长编码检测
- UNC 路径阻止
- Windows 驱动器路径限制

性能优化:
- LRU 缓存路径验证结果
- 预编译正则表达式

使用:
- builtin_tools: file_read, file_write, file_edit
- sandbox: 文件系统隔离检查
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
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    DEFAULT_WORK_DIR = Path.home() / ".seed"
    ALLOWED_DIRS_RAW = [
        DEFAULT_WORK_DIR,
        PROJECT_ROOT,
        Path.home() / "Documents",
    ]


# 缓存已解析的 ALLOWED_DIRS（避免每次调用 resolve()）
def _resolve_allowed_dirs() -> list[str]:
    """解析并缓存 ALLOWED_DIRS（模块初始化时调用）"""
    resolved = []
    for allowed in ALLOWED_DIRS_RAW:
        try:
            resolved.append(str(Path(str(allowed)).resolve()))
        except Exception as e:
            logger.debug(f"Failed to resolve allowed dir '{allowed}': {e}")
    return resolved


ALLOWED_DIRS: list[str] = _resolve_allowed_dirs()

# 缓存 DEFAULT_WORK_DIR 和 PROJECT_ROOT 的解析结果
DEFAULT_WORK_DIR_RESOLVED = str(DEFAULT_WORK_DIR.resolve())
PROJECT_ROOT_RESOLVED = str(PROJECT_ROOT.resolve())


# 预编译正则表达式（性能优化）
_RE_WINDOWS_DRIVE = re.compile(r"^[a-zA-Z]:[/\\]")
_RE_DOUBLE_DOT = re.compile(r"\.\.")  # 快速检测 .. 序列

# URL 编码攻击模式（包括双重编码和 UTF-8 过长编码）
_RE_URL_ENCODED = re.compile(r"%[0-9a-fA-F]{2}", re.IGNORECASE)
_RE_DOUBLE_URL_ENCODED = re.compile(r"%25[0-9a-fA-F]{2}", re.IGNORECASE)
# UTF-8 过长编码：\xc0\xae 或 \xe0\x80\xae 等变体表示 '.'
_RE_UTF8_OVERLONG = re.compile(
    r"[\xc0-\xc1][\x80-\xbf]|\xe0\x80[\xae\xaf]|\xed\xa0[\x80-\xbf]"
)


@functools.lru_cache(maxsize=1024)
def is_path_in_allowed_dirs(resolved_path: str) -> bool:
    """检查路径是否在允许目录内（使用缓存）

    缓存大小 1024 覆盖高频访问路径，减少重复验证开销。

    Args:
        resolved_path: 已解析的绝对路径字符串

    Returns:
        是否在允许目录内
    """
    return any(resolved_path.startswith(allowed) for allowed in ALLOWED_DIRS)


def validate_path_safety(path: str) -> tuple[bool, str]:
    """
    验证路径安全性，防止路径遍历攻击。

    Args:
        path: 原始路径字符串

    Returns:
        (is_safe, error_message): 安全返回 (True, ""), 不安全返回 (False, 错误信息)
    """
    # 1. URL 编码绕过检测（单层和双重编码）
    path_lower = path.lower()
    if _RE_URL_ENCODED.search(path_lower) or _RE_DOUBLE_URL_ENCODED.search(path_lower):
        # 解码后检查是否包含危险字符
        try:
            from urllib.parse import unquote

            decoded_once = unquote(path)
            decoded_twice = unquote(decoded_once)
            for decoded in [path, decoded_once, decoded_twice]:
                if ".." in decoded or decoded.startswith(("/", "\\")):
                    logger.warning(
                        f"URL-encoded path traversal attempt blocked: {path} -> {decoded}"
                    )
                    return (
                        False,
                        f"URL-encoded path blocked: '{path[:50]}...' - decoded path contains traversal patterns",
                    )
        except Exception as e:
            # 解码失败时保守拒绝
            logger.warning(
                f"URL-encoded path blocked (decode failed: {path}, error: {type(e).__name__})"
            )
            return (
                False,
                f"URL-encoded path blocked: '{path[:50]}...' - cannot safely decode",
            )

    # 2. UTF-8 过长编码检测（绕过技术）
    if _RE_UTF8_OVERLONG.search(path):
        logger.warning(f"UTF-8 overlong encoding detected: {path}")
        return (
            False,
            f"UTF-8 overlong encoding blocked: '{path[:50]}...' - potential path traversal attempt",
        )

    # 3. 快速检测 .. 序列（使用预编译正则）
    if _RE_DOUBLE_DOT.search(path):
        # 计算遍历深度
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
            return (
                False,
                f"Path traversal blocked: '{path}' contains '..' sequences that escape allowed directories",
            )

    # Windows 特殊攻击模式
    if os.name == "nt":
        # 检查驱动器字母模式
        if _RE_WINDOWS_DRIVE.match(path):
            try:
                resolved = str(Path(path).resolve())
                if is_path_in_allowed_dirs(resolved):
                    return True, ""
            except Exception as e:
                logger.debug(f"Failed to resolve Windows drive path '{path}': {e}")
            logger.warning(f"Windows drive path outside allowed dirs: {path}")
            return False, f"Windows drive path '{path}' is outside allowed directories"

        # 检查 UNC 路径
        if path.startswith(("\\\\", "//")):
            logger.warning(f"UNC path blocked: {path}")
            return False, f"UNC path '{path}' is not allowed for security reasons"

    # 检查绝对路径是否在允许范围内（使用缓存）
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
    # 先展开 ~ 为用户主目录
    if path.startswith("~"):
        path = os.path.expanduser(path)

    # 安全验证
    is_safe, error = validate_path_safety(path)
    if not is_safe:
        raise ValueError(error)

    if os.path.isabs(path):
        return path

    # 相对路径：优先从 .seed 目录解析
    seed_path = DEFAULT_WORK_DIR / path
    try:
        resolved_seed = str(seed_path.resolve())
        # 使用缓存检查
        if (
            resolved_seed.startswith((DEFAULT_WORK_DIR_RESOLVED, PROJECT_ROOT_RESOLVED))
        ) and seed_path.exists():
            return resolved_seed
    except Exception as e:
        logger.debug(f"Failed to resolve seed path '{path}': {e}")

    # 再从项目根目录解析
    project_path = PROJECT_ROOT / path
    try:
        resolved_project = str(project_path.resolve())
        if resolved_project.startswith(PROJECT_ROOT_RESOLVED) and project_path.exists():
            return resolved_project
    except Exception as e:
        logger.debug(f"Failed to resolve project path '{path}': {e}")

    # 如果都不存在，使用 .seed 目录作为默认目标
    final_path = str(DEFAULT_WORK_DIR / path)
    final_resolved = str(Path(final_path).resolve())
    if not final_resolved.startswith(DEFAULT_WORK_DIR_RESOLVED):
        raise ValueError(f"Resolved path escapes allowed directories: {final_path}")

    return final_path


# 公共导出
__all__ = [
    "ALLOWED_DIRS",
    "DEFAULT_WORK_DIR",
    "PROJECT_ROOT",
    "is_path_in_allowed_dirs",
    "resolve_path",
    "validate_path_safety",
]
