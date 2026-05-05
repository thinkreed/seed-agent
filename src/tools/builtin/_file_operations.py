"""
文件操作工具

基于 qwen-code DeclarativeTool 设计：
- file_read: 文件读取（带行号、编码检测）
- file_write: 文件写入（覆盖/追加）
- file_edit: 文件编辑（字符串替换）

安全特性：
- 路径安全验证
- 编码自动检测
- 输出截断
"""

import logging
from pathlib import Path

from ._path_validation import _resolve_path
from .utils import safe_int_convert

logger = logging.getLogger("seed_agent.file")


def file_read(path: str, start: int = 1, count: int = 100) -> str:
    """
    Read file content with line numbers.
    支持自动编码检测 (UTF-8, GBK, GB2312, Latin-1)。

    Args:
        path: File path to read (absolute or relative to .seed directory).
        start: Start line number (1-based).
        count: Number of lines to read.

    Returns:
        File content with line numbers, or error message.
    """
    try:
        start = safe_int_convert(start, default=1, min_val=1)
        count = safe_int_convert(count, default=100, min_val=1)

        resolved_path = _resolve_path(path)
        content = None
        detected_encoding = "utf-8"

        # 尝试多种编码
        for enc in ["utf-8", "gbk", "gb2312", "latin-1"]:
            try:
                with open(resolved_path, encoding=enc) as f:
                    content = f.readlines()
                detected_encoding = enc
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            return f"Error: Unable to decode file {path} with supported encodings"

        total_lines = len(content)
        start_idx = max(0, start - 1)
        end_idx = min(total_lines, start_idx + count)
        selected = content[start_idx:end_idx]

        if not selected:
            return f"Empty range: lines {start}-{start + count - 1} (file has {total_lines} lines)"

        result = "".join(
            f"{i + start_idx + 1}|{line}" for i, line in enumerate(selected)
        )
        enc_note = f" (decoded as {detected_encoding})" if detected_encoding != "utf-8" else ""
        result += f"\n--- File: {resolved_path}{enc_note}, Lines: {start}-{end_idx}/{total_lines} ---"
        return result

    except FileNotFoundError:
        return f"Error: File not found - {path}"
    except Exception as e:
        return f"Error reading file: {e!s}"


def file_write(path: str, content: str, mode: str = "overwrite") -> str:
    """
    Write content to a file.

    Args:
        path: File path to write (absolute or relative to .seed directory).
        content: Content to write.
        mode: Write mode - 'overwrite' (default) or 'append'.

    Returns:
        Success message or error.
    """
    try:
        resolved_path = _resolve_path(path)

        write_mode = "w" if mode == "overwrite" else "a"
        Path(resolved_path).parent.mkdir(parents=True, exist_ok=True)

        with open(resolved_path, write_mode, encoding="utf-8") as f:
            f.write(content)

        action = "written" if mode == "overwrite" else "appended"
        return f"Successfully {action} to {resolved_path} ({len(content)} chars)"

    except Exception as e:
        error_type = type(e).__name__
        logger.exception(f"Full error writing to '{resolved_path}': {error_type}")
        return f"Error writing to '{resolved_path}': {error_type} - {str(e)[:200]}"


def file_edit(path: str, old_str: str, new_str: str, replace_all: bool = False) -> str:
    """
    Edit file by replacing text.

    Args:
        path: File path to edit (absolute or relative to .seed directory).
        old_str: Text to find and replace (must be exact match).
        new_str: New text to insert.
        replace_all: If True, replace all occurrences; else replace first.

    Returns:
        Success message with change details, or error.
    """
    try:
        resolved_path = _resolve_path(path)

        with open(resolved_path, encoding="utf-8") as f:
            content = f.read()

        if old_str not in content:
            return f"Error: Text not found in file - '{old_str[:50]}...'"

        if replace_all:
            count = content.count(old_str)
            new_content = content.replace(old_str, new_str)
        else:
            count = 1
            new_content = content.replace(old_str, new_str, 1)

        with open(resolved_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"Successfully edited {resolved_path}: replaced {count} occurrence(s)"

    except FileNotFoundError:
        return f"Error: File not found - {path}"
    except Exception as e:
        logger.exception("file_edit failed")
        return f"Error editing file: {e!s}"