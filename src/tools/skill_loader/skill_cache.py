"""
磁盘快照缓存模块 - Skill 元数据的持久化缓存

使用 mtime+size manifest 检测文件变更，实现缓存失效机制。
"""

import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from src.tools.skill_loader._cache_converters import (
    convert_lists_to_sets,
    convert_sets_to_lists,
)
from src.tools.skill_loader._cache_paths import ensure_cache_paths, get_snapshot_path

logger = logging.getLogger(__name__)


def build_manifest(skills_dir: Path) -> str:
    """
    构建技能目录的 manifest (mtime + size) 用于缓存失效检测

    Args:
        skills_dir: 技能目录路径

    Returns:
        SHA256 hash 字符串，空目录返回空字符串
    """
    if not skills_dir.exists():
        return ""

    manifest = {}
    for skill_dir in sorted(skills_dir.iterdir()):
        if skill_dir.is_dir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                stat = skill_file.stat()
                manifest[str(skill_dir.name)] = {
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                }

    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def load_snapshot(skills_dir: Path) -> dict | None:
    """
    从磁盘加载缓存快照

    Args:
        skills_dir: 技能目录路径

    Returns:
        快照字典，若快照不存在或已失效返回 None
    """
    _cache_dir, snapshot_path = ensure_cache_paths()
    try:
        if not snapshot_path.exists():
            return None

        with open(snapshot_path, encoding="utf-8") as f:
            snapshot = json.load(f)

        # 检查 manifest 是否匹配
        current_manifest = build_manifest(skills_dir)
        if snapshot.get("manifest") != current_manifest:
            logger.debug("Skill cache snapshot expired (manifest mismatch)")
            return None

        # 转换特定字段为 set（用于 O(1) 查找）
        if "skills" in snapshot:
            snapshot["skills"] = convert_lists_to_sets(snapshot["skills"])

        logger.debug(
            f"Skill cache snapshot loaded: {len(snapshot.get('skills', {}))} skills"
        )
        return snapshot
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse skill cache snapshot: {type(e).__name__}: {e}")
        return None
    except OSError as e:
        logger.warning(f"Failed to load skill cache snapshot: {type(e).__name__}: {e}")
        return None


def save_snapshot(skills_dir: Path, skills_meta: dict) -> None:
    """
    保存缓存快照到磁盘

    使用原子写入模式，先写入临时文件再 rename。
    """
    cache_dir, snapshot_path = ensure_cache_paths()
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 转换 set 为 list（JSON 序列化兼容）
        serializable_meta = convert_sets_to_lists(skills_meta)

        snapshot = {
            "manifest": build_manifest(skills_dir),
            "timestamp": datetime.now(UTC).isoformat(),
            "skills": serializable_meta,
        }

        # 原子写入
        tmp_path = snapshot_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, snapshot_path)

        logger.debug(f"Skill cache snapshot saved: {len(skills_meta)} skills")
    except OSError as e:
        logger.warning(f"Failed to save skill cache snapshot: {type(e).__name__}: {e}")


def clear_snapshot() -> None:
    """清除磁盘快照 (在 skill 被 patch 后调用)"""
    _cache_dir, snapshot_path = ensure_cache_paths()
    try:
        if snapshot_path.exists():
            snapshot_path.unlink()
            logger.debug("Skill cache snapshot cleared")
    except OSError as e:
        logger.warning(f"Failed to clear skill cache snapshot: {type(e).__name__}: {e}")


# 兼容性别名（供旧测试使用）
_build_manifest = build_manifest

# 兼容旧代码的全局变量引用
SNAPSHOT_PATH = None


__all__ = [
    "SNAPSHOT_PATH",
    "_build_manifest",
    "build_manifest",
    "clear_snapshot",
    "load_snapshot",
    "save_snapshot",
    "get_snapshot_path",
]