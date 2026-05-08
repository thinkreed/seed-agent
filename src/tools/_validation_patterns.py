"""
路径安全模式检测 - Path Validation Pattern Detectors

提供预编译正则表达式和安全检测函数。
"""

import re

# 预编译正则表达式
_RE_WINDOWS_DRIVE = re.compile(r"^[a-zA-Z]:[/\\]")
_RE_DOUBLE_DOT = re.compile(r"\.\.")  # 快速检测 .. 序列
_RE_URL_ENCODED = re.compile(r"%[0-9a-fA-F]{2}", re.IGNORECASE)
_RE_DOUBLE_URL_ENCODED = re.compile(r"%25[0-9a-fA-F]{2}", re.IGNORECASE)
# UTF-8 过长编码：\xc0\xae 或 \xe0\x80\xae 等变体表示 '.'
_RE_UTF8_OVERLONG = re.compile(r"[\xc0-\xc1][\x80-\xbf]|\xe0\x80[\xae\xaf]|\xed\xa0[\x80-\xbf]")


def detect_url_encoded_traversal(path: str) -> tuple[bool, str]:
    """检测 URL 编码绕过攻击

    Args:
        path: 原始路径字符串

    Returns:
        (is_blocked, error_message): 检测到攻击返回 (True, 错误信息)
    """
    path_lower = path.lower()
    if not (_RE_URL_ENCODED.search(path_lower) or _RE_DOUBLE_URL_ENCODED.search(path_lower)):
        return False, ""

    # 解码后检查是否包含危险字符
    try:
        from urllib.parse import unquote

        decoded_once = unquote(path)
        decoded_twice = unquote(decoded_once)
        for decoded in [path, decoded_once, decoded_twice]:
            if ".." in decoded or decoded.startswith(("/", "\\")):
                return (
                    True,
                    f"URL-encoded path blocked: '{path[:50]}...' - decoded path contains traversal patterns",
                )
    except Exception:
        return (
            True,
            f"URL-encoded path blocked: '{path[:50]}...' - cannot safely decode",
        )
    return False, ""


def detect_utf8_overlong(path: str) -> tuple[bool, str]:
    """检测 UTF-8 过长编码攻击

    Args:
        path: 原始路径字符串

    Returns:
        (is_blocked, error_message): 检测到攻击返回 (True, 错误信息)
    """
    if _RE_UTF8_OVERLONG.search(path):
        return (
            True,
            f"UTF-8 overlong encoding blocked: '{path[:50]}...' - potential path traversal attempt",
        )
    return False, ""


def detect_double_dot_traversal(path: str) -> tuple[bool, str]:
    """检测 .. 序列路径遍历攻击

    Args:
        path: 原始路径字符串

    Returns:
        (is_blocked, error_message): 检测到攻击返回 (True, 错误信息)
    """
    if not _RE_DOUBLE_DOT.search(path):
        return False, ""

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
        return (
            True,
            f"Path traversal blocked: '{path}' contains '..' sequences that escape allowed directories",
        )
    return False, ""


def is_windows_drive_path(path: str) -> bool:
    """检查是否为 Windows 驱动器路径"""
    return bool(_RE_WINDOWS_DRIVE.match(path))


def is_unc_path(path: str) -> bool:
    """检查是否为 UNC 路径"""
    return path.startswith(("\\\\", "//"))


def validate_windows_path(
    path: str,
    is_path_in_allowed_dirs,
) -> tuple[bool, str, bool]:
    """验证 Windows 特殊路径安全性

    Args:
        path: 原始路径字符串
        is_path_in_allowed_dirs: 检查路径是否在允许目录内的函数

    Returns:
        (is_safe, error_message, was_handled):
        - was_handled=True: 路径是 Windows 特殊路径，已处理
        - was_handled=False: 不是 Windows 特殊路径，需要继续其他检查
    """
    # 检查驱动器字母模式
    if is_windows_drive_path(path):
        try:
            from pathlib import Path
            resolved = str(Path(path).resolve())
            if is_path_in_allowed_dirs(resolved):
                return True, "", True  # 有效路径
        except Exception:
            pass
        return False, f"Windows drive path '{path}' is outside allowed directories", True

    # 检查 UNC 路径
    if is_unc_path(path):
        return False, f"UNC path '{path}' is not allowed for security reasons", True

    return True, "", False  # 不是 Windows 特殊路径


__all__ = [
    "detect_double_dot_traversal",
    "detect_utf8_overlong",
    "detect_url_encoded_traversal",
    "is_unc_path",
    "is_windows_drive_path",
    "validate_windows_path",
]