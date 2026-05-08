"""
磁盘快照缓存模块 - Skill 元数据的持久化缓存

使用 mtime+size manifest 检测文件变更，实现缓存失效机制。
"""

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ._skill_cache_paths import build_manifest, ensure_cache_paths, SNAPSHOT_PATH

logger = logging.getLogger(__name__)

# 向后兼容别名
_ensure_cache_paths = ensure_cache_paths


def _convert_lists_to_sets_for_meta(skills_meta: dict) -> dict:
    """将 skills_meta 中的 list 字段转换为 set（支持 O(1) 查找）"""
    set_fields = {"triggers_lower", "desc_words"}

    for meta in skills_meta.values():
        for field in set_fields:
            if field in meta and isinstance(meta[field], list):
                meta[field] = set(meta[field])

    return skills_meta


def _convert_sets_to_lists(obj: dict | list | set | Any) -> dict | list | Any:
    """
    递归转换 dict 中的 set 为 list（JSON 序列化兼容）

    Args:
        obj: 待转换的对象

    Returns:
        JSON 可序列化的对象
    """
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, dict):
        return {k: _convert_sets_to_lists(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_sets_to_lists(item) for item in obj]
    return obj


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
            snapshot["skills"] = _convert_lists_to_sets_for_meta(snapshot["skills"])

        logger.debug(f"Skill cache snapshot loaded: {len(snapshot.get('skills', {}))} skills")
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

    Args:
        skills_dir: 技能目录路径
        skills_meta: 技能元数据字典
    """
    cache_dir, snapshot_path = ensure_cache_paths()
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 转换 set 为 list（JSON 序列化兼容）
        serializable_meta = _convert_sets_to_lists(skills_meta)

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
    """清除磁盘快照（在 skill 被 patch 后调用）"""
    _cache_dir, snapshot_path = ensure_cache_paths()
    try:
        if snapshot_path.exists():
            snapshot_path.unlink()
            logger.debug("Skill cache snapshot cleared")
    except OSError as e:
        logger.warning(f"Failed to clear skill cache snapshot: {type(e).__name__}: {e}")


__all__ = [
    "build_manifest",
    "load_snapshot",
    "save_snapshot",
    "clear_snapshot",
    "SNAPSHOT_PATH",
]