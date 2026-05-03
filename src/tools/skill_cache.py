"""
磁盘快照缓存模块 - Skill 元数据的持久化缓存

使用 mtime+size manifest 检测文件变更，实现缓存失效机制。
"""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

# 缓存路径配置
CACHE_DIR = Path(os.path.expanduser("~")) / ".seed" / "cache"
SNAPSHOT_PATH = CACHE_DIR / "skills_snapshot.json"


def build_manifest(skills_dir: Path) -> str:
    """
    构建技能目录的 manifest (mtime + size) 用于缓存失效检测

    Args:
        skills_dir: 技能目录路径

    Returns:
        MD5 hash 字符串，空目录返回空字符串
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

    return hashlib.md5(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def _convert_lists_to_sets_for_meta(skills_meta: dict) -> dict:
    """
    将 skills_meta 中的特定字段从 list 转换回 set

    用于加载快照后恢复内存中的 set 类型（支持 O(1) 查找）。

    Args:
        skills_meta: 从 JSON 加载的技能元数据

    Returns:
        包含 set 类型字段的元数据
    """
    set_fields = {"triggers_lower", "desc_words"}  # 需要转为 set 的字段名

    for skill_name, meta in skills_meta.items():
        for field in set_fields:
            if field in meta and isinstance(meta[field], list):
                meta[field] = set(meta[field])

    return skills_meta


def load_snapshot(skills_dir: Path) -> dict | None:
    """
    从磁盘加载缓存快照

    Args:
        skills_dir: 技能目录路径

    Returns:
        快照字典，若快照不存在或已失效返回 None

    Note:
        加载后会自动将 triggers_lower 和 desc_words 从 list 转回 set，
        以支持内存中的 O(1) 快速查找。
    """
    try:
        if not SNAPSHOT_PATH.exists():
            return None

        with open(SNAPSHOT_PATH, encoding="utf-8") as f:
            snapshot = json.load(f)

        # 检查 manifest 是否匹配
        current_manifest = build_manifest(skills_dir)
        if snapshot.get("manifest") != current_manifest:
            return None  # 文件已变更，快照失效

        # 转换特定字段为 set（用于 O(1) 查找）
        if "skills" in snapshot:
            snapshot["skills"] = _convert_lists_to_sets_for_meta(snapshot["skills"])

        return snapshot
    except (json.JSONDecodeError, OSError):
        return None


def _convert_sets_to_lists(obj: dict | list | set | Any) -> dict | list | Any:
    """
    递归转换 dict 中的 set 为 list（JSON 序列化兼容）

    自动将 set 类型字段转换为 list 以支持 JSON 序列化。

    Args:
        obj: 待转换的对象（dict、list、set 或其他）

    Returns:
        JSON 可序列化的对象
    """
    if isinstance(obj, set):
        return sorted(obj)  # 排序保证一致性
    if isinstance(obj, dict):
        return {k: _convert_sets_to_lists(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_sets_to_lists(item) for item in obj]
    return obj


def save_snapshot(skills_dir: Path, skills_meta: dict) -> None:
    """
    保存缓存快照到磁盘

    使用原子写入模式，先写入临时文件再 rename。
    自动将 set 类型字段转换为 list 以支持 JSON 序列化。

    Args:
        skills_dir: 技能目录路径
        skills_meta: 技能元数据字典

    Note:
        skills_meta 中的 set 类型字段（如 triggers_lower, desc_words）
        会自动转换为 list 以支持 JSON 序列化。
    """
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # 转换 set 为 list（JSON 序列化兼容）
        serializable_meta = _convert_sets_to_lists(skills_meta)

        snapshot = {
            "manifest": build_manifest(skills_dir),
            "timestamp": datetime.now().isoformat(),
            "skills": serializable_meta,
        }

        # 原子写入
        tmp_path = SNAPSHOT_PATH.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, SNAPSHOT_PATH)
    except OSError:
        pass


def clear_snapshot() -> None:
    """清除磁盘快照 (在 skill 被 patch 后调用)"""
    try:
        if SNAPSHOT_PATH.exists():
            SNAPSHOT_PATH.unlink()
    except OSError:
        pass
