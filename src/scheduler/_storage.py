"""定时任务存储模块

包含任务存储相关功能：
- _get_tasks_dir, _get_tasks_file
- load_tasks, save_tasks
"""

import contextlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

logger = logging.getLogger("seed_agent")

# 全局变量用于测试 override（None 表示使用默认路径）
_TASKS_DIR_OVERRIDE: Path | None = None


def _set_tasks_dir_override(path: Path | None) -> None:
    """设置任务目录 override（用于测试）"""
    global _TASKS_DIR_OVERRIDE
    _TASKS_DIR_OVERRIDE = path


def _get_tasks_dir() -> Path:
    """获取任务存储目录（动态）"""
    if _TASKS_DIR_OVERRIDE is not None:
        return _TASKS_DIR_OVERRIDE
    try:
        from src.shared_config import get_paths_config
        return get_paths_config().tasks_dir
    except RuntimeError:
        # PathsConfig 未初始化时使用 fallback
        return Path.home() / ".seed" / "tasks"


def _get_tasks_file() -> Path:
    """获取任务文件路径"""
    return _get_tasks_dir() / "scheduled_tasks.json"


def load_tasks(tasks_file: Path) -> dict:
    """加载已保存的任务

    Args:
        tasks_file: 任务文件路径

    Returns:
        任务数据字典
    """
    tasks_dir = tasks_file.parent
    tasks_dir.mkdir(parents=True, exist_ok=True)

    if tasks_file.exists():
        try:
            with tasks_file.open(encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load tasks file: {e}, starting fresh")
            # Corrupted file: backup and start fresh
            backup_path = tasks_file.with_suffix(".json.bak")
            with contextlib.suppress(OSError):
                tasks_file.replace(backup_path)
    return {"tasks": []}


def save_tasks(tasks: dict, tasks_file: Path) -> None:
    """保存任务到文件（原子写入模式）

    使用临时文件+原子替换模式，避免写入中途崩溃导致数据损坏。

    Args:
        tasks: 任务数据
        tasks_file: 任务文件路径
    """
    tasks_dir = tasks_file.parent
    tasks_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "updated_at": datetime.now(tz=UTC).isoformat(),
        "tasks": tasks.get("tasks", []),
    }

    # 原子写入：先写临时文件，再替换原文件
    temp_file = tasks_file.with_suffix(".tmp")
    try:
        with temp_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # 原子替换（replace 在 POSIX 上是原子操作，Windows 上尽量保证）
        temp_file.replace(tasks_file)
    except OSError:
        logger.exception("Failed to save tasks")
        # 清理临时文件
        if temp_file.exists():
            with contextlib.suppress(OSError):
                temp_file.unlink()
        raise

    logger.info(f"Saved {len(data['tasks'])} scheduled tasks")


def get_log_file() -> Path:
    """获取执行日志文件路径"""
    return _get_tasks_dir() / "execution_log.jsonl"


__all__ = [
    "_get_tasks_dir",
    "_get_tasks_file",
    "load_tasks",
    "save_tasks",
    "get_log_file",
]