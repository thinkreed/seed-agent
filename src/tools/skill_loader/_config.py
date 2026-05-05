"""
Skill Loader 配置和常量

职责:
- 配置常量定义
- 平台映射
- Memory Graph 配置
"""

import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# 预编译正则表达式（性能优化）
_RE_EN_WORD = re.compile(r"[a-zA-Z0-9_]+")
_RE_EN_WORD_HYPHEN = re.compile(r"[a-zA-Z0-9_-]+")
_RE_CN_WORD = re.compile(r"[\u4e00-\u9fa5]+")

# LRU 缓存配置
MAX_LOADED_SKILL_CACHE = 5

# 内容截取限制
MAX_COMPACT_CONTENT = 500


def _get_skills_dir() -> Path:
    """获取技能目录"""
    try:
        from src.shared_config import get_paths_config
        return get_paths_config().memory_dir / "skills"
    except RuntimeError:
        return Path.home() / ".seed" / "memory" / "skills"


SKILLS_DIR: Path | None = None


def _ensure_skills_dir() -> Path:
    """确保技能目录已初始化"""
    global SKILLS_DIR
    if SKILLS_DIR is None:
        SKILLS_DIR = _get_skills_dir()
    return SKILLS_DIR


# 平台映射
PLATFORM_MAP = {
    "win32": "windows",
    "linux": "linux",
    "darwin": "macos",
    "windows": "windows",
    "macos": "macos",
}

# 当前平台
CURRENT_PLATFORM = PLATFORM_MAP.get(sys.platform, sys.platform)


# Memory Graph 配置
try:
    from src.shared_config import get_memory_graph_config
    _mg_config = get_memory_graph_config()
    MEMORY_GRAPH_CONFIG = {
        "half_life_days": _mg_config.half_life_days,
        "ban_threshold": _mg_config.ban_threshold,
        "min_attempts_for_ban": _mg_config.min_attempts_for_ban,
        "memory_weight": _mg_config.memory_weight,
        "trigger_weight": _mg_config.trigger_weight,
        "cold_start_penalty": _mg_config.cold_start_penalty,
        "recent_boost_factor": _mg_config.recent_boost_factor,
        "recent_days": _mg_config.recent_days,
        "enabled": True,
    }
except ImportError:
    MEMORY_GRAPH_CONFIG = {
        "half_life_days": 30,
        "ban_threshold": 0.18,
        "min_attempts_for_ban": 2,
        "memory_weight": 0.6,
        "trigger_weight": 0.4,
        "cold_start_penalty": 0.5,
        "recent_boost_factor": 0.2,
        "recent_days": 30,
        "enabled": True,
    }


__all__ = [
    "CURRENT_PLATFORM",
    "MAX_COMPACT_CONTENT",
    "MAX_LOADED_SKILL_CACHE",
    "MEMORY_GRAPH_CONFIG",
    "PLATFORM_MAP",
    "_RE_CN_WORD",
    "_RE_EN_WORD",
    "_RE_EN_WORD_HYPHEN",
    "_ensure_skills_dir",
    "_get_skills_dir",
]