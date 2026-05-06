"""
记忆提取光标机制

跟踪已处理偏移量，避免重复提取：
- 基于文件的光标存储
- 原子读写操作
- 自动过期清理

参考: Qwen-Code 提取光标设计 (extract-cursor.json)
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("seed_agent")

# 光标过期时间（1 小时）
CURSOR_STALE_MS = 60 * 60 * 1000


class ExtractCursor:
    """记忆提取光标

    用于跟踪记忆提取进度，避免重复处理：
    - 记录已处理的偏移量
    - 支持多种提取源（session_db, jsonl 等）
    - 自动过期清理

    Usage:
        cursor = ExtractCursor(cursor_dir)
        offset = cursor.get_offset("session_db")
        # 处理从 offset 开始的新数据
        new_offset = process_session_data(offset)
        cursor.set_offset("session_db", new_offset)
    """

    def __init__(self, cursor_dir: Optional[Path] = None) -> None:
        """初始化提取光标

        Args:
            cursor_dir: 光标文件目录，默认为 ~/.seed/cursors/
        """
        if cursor_dir is None:
            home = Path.home()
            seed_dir = home / ".seed"
            seed_dir.mkdir(parents=True, exist_ok=True)
            cursor_dir = seed_dir / "cursors"

        self._cursor_dir = cursor_dir
        self._cursor_dir.mkdir(parents=True, exist_ok=True)

    def _get_cursor_file(self, source: str) -> Path:
        """获取指定源的光标文件路径"""
        return self._cursor_dir / f"{source}_cursor.json"

    def get_offset(self, source: str) -> int:
        """获取指定源的已处理偏移量

        Args:
            source: 提取源名称（如 'session_db', 'jsonl'）

        Returns:
            已处理的偏移量，如果不存在或过期则返回 0
        """
        cursor_file = self._get_cursor_file(source)

        if not cursor_file.exists():
            return 0

        try:
            data = json.loads(cursor_file.read_text(encoding="utf-8"))
            # 检查是否过期
            if self._is_stale(data):
                logger.info(f"Cursor for {source} is stale, resetting")
                self._force_reset(source)
                return 0
            return data.get("offset", 0)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read cursor for {source}: {e}")
            return 0

    def set_offset(self, source: str, offset: int) -> None:
        """设置指定源的已处理偏移量

        Args:
            source: 提取源名称
            offset: 新的偏移量
        """
        cursor_file = self._get_cursor_file(source)
        data = {
            "source": source,
            "offset": offset,
            "timestamp": time.time(),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        try:
            cursor_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.debug(f"Updated cursor for {source}: offset={offset}")
        except OSError as e:
            logger.error(f"Failed to write cursor for {source}: {e}")

    def reset_offset(self, source: str) -> None:
        """重置指定源的偏移量"""
        self.set_offset(source, 0)
        logger.info(f"Reset cursor for {source}")

    def _is_stale(self, data: dict) -> bool:
        """检查光标是否过期"""
        timestamp = data.get("timestamp", 0)
        now = time.time()
        return (now - timestamp) > (CURSOR_STALE_MS / 1000)

    def _force_reset(self, source: str) -> None:
        """强制重置光标（用于清理过期光标）"""
        cursor_file = self._get_cursor_file(source)
        try:
            cursor_file.unlink(missing_ok=True)
        except OSError as e:
            logger.error(f"Failed to reset cursor for {source}: {e}")

    def get_all_cursors(self) -> dict[str, dict]:
        """获取所有光标信息"""
        cursors = {}
        for cursor_file in self._cursor_dir.glob("*_cursor.json"):
            try:
                data = json.loads(cursor_file.read_text(encoding="utf-8"))
                source = data.get("source", cursor_file.stem.replace("_cursor", ""))
                cursors[source] = data
            except (json.JSONDecodeError, OSError):
                continue
        return cursors

    def cleanup_stale_cursors(self) -> int:
        """清理所有过期光标

        Returns:
            清理的光标数量
        """
        cleaned = 0
        for cursor_file in self._cursor_dir.glob("*_cursor.json"):
            try:
                data = json.loads(cursor_file.read_text(encoding="utf-8"))
                if self._is_stale(data):
                    cursor_file.unlink(missing_ok=True)
                    cleaned += 1
                    logger.info(f"Cleaned stale cursor: {cursor_file.name}")
            except (json.JSONDecodeError, OSError):
                continue
        return cleaned


def get_extract_cursor(project_root: Optional[Path] = None) -> ExtractCursor:
    """获取提取光标的便捷函数

    Args:
        project_root: 项目根目录，用于确定光标目录

    Returns:
        ExtractCursor 实例
    """
    if project_root is not None:
        cursor_dir = project_root / ".seed" / "cursors"
    else:
        cursor_dir = None

    return ExtractCursor(cursor_dir)


__all__ = [
    "ExtractCursor",
    "get_extract_cursor",
    "CURSOR_STALE_MS",
]