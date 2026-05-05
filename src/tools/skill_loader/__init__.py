"""
渐进式 Skill 加载器

核心优化:
1. 两级缓存 (进程内 LRU + 磁盘快照)
2. 条件激活 (requires_tools, fallback_for, platforms)
3. Prompt Injection 安全扫描
4. 分类分组索引
5. 三级渐进式披露: 索引(Tier1) → 内容(Tier2) → 参考文件(Tier3)

使用方法:
    from src.tools.skill_loader import SkillLoader, load_skill

    loader = SkillLoader()
    content = loader.load_skill_content("my-skill")
"""

# 主类
from ._skillloader import SkillLoader

# API 函数
from ._api import get_loader, list_skills, load_skill, register_skill_tools, search_skill, _global_loader, _set_global_loader

# 类型
from ._types import SkillMeta, SkillMetadata

# 缓存
from ._cache import SkillContentCache

# 加载器函数
from ._loader import get_gene_slice, load_skill_content

# 配置
from ._config import MEMORY_GRAPH_CONFIG, PLATFORM_MAP, MAX_LOADED_SKILL_CACHE

# 磁盘缓存
from .skill_cache import SNAPSHOT_PATH, build_manifest, clear_snapshot, load_snapshot, save_snapshot

# 安全
from .skill_security import INJECTION_PATTERNS, scan_for_injections, validate_path_within_dir, validate_skill_structure

# 兼容别名
_get_loader = get_loader
_build_manifest = build_manifest  # 内部函数兼容别名
_scan_for_injections = scan_for_injections  # 内部函数兼容别名
_validate_skill_structure = validate_skill_structure  # 内部函数兼容别名


__all__ = [
    "SkillLoader",
    "SkillMeta",
    "SkillMetadata",
    "SkillContentCache",
    "get_loader",
    "_get_loader",
    "_global_loader",
    "_set_global_loader",
    "list_skills",
    "load_skill",
    "load_skill_content",
    "get_gene_slice",
    "register_skill_tools",
    "search_skill",
    "MEMORY_GRAPH_CONFIG",
    "PLATFORM_MAP",
    "MAX_LOADED_SKILL_CACHE",
    "SNAPSHOT_PATH",
    "build_manifest",
    "_build_manifest",
    "clear_snapshot",
    "load_snapshot",
    "save_snapshot",
    "INJECTION_PATTERNS",
    "scan_for_injections",
    "_scan_for_injections",
    "validate_skill_structure",
    "_validate_skill_structure",
    "validate_path_within_dir",
]