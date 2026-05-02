"""
磁盘快照缓存模块 - Skill 元数据的持久化缓存

使用 mtime+size manifest 检测文件变更，实现缓存失效机制。
"""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

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


def load_snapshot(skills_dir: Path) -> dict | None:
    """
    从磁盘加载缓存快照
    
    Args:
        skills_dir: 技能目录路径
        
    Returns:
        快照字典，若快照不存在或已失效返回 None
    """
    try:
        if not SNAPSHOT_PATH.exists():
            return None

        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            snapshot = json.load(f)

        # 检查 manifest 是否匹配
        current_manifest = build_manifest(skills_dir)
        if snapshot.get("manifest") != current_manifest:
            return None  # 文件已变更，快照失效

        return snapshot
    except (json.JSONDecodeError, OSError):
        return None


def save_snapshot(skills_dir: Path, skills_meta: dict) -> None:
    """
    保存缓存快照到磁盘
    
    使用原子写入模式，先写入临时文件再 rename。
    
    Args:
        skills_dir: 技能目录路径
        skills_meta: 技能元数据字典
    """
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        snapshot = {
            "manifest": build_manifest(skills_dir),
            "timestamp": datetime.now().isoformat(),
            "skills": skills_meta,
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
