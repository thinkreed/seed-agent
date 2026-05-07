"""
渐进式 Skill 加载器

核心优化:
1. 两级缓存 (进程内 LRU + 磁盘快照)
2. 条件激活 (requires_tools, fallback_for, platforms)
3. Prompt Injection 安全扫描
4. 分类分组索引
5. 三级渐进式披露: 索引(Tier1) → 内容(Tier2) → 参考文件(Tier3)

Wiki 知识落地 P2 (Hermes-Agent):
6. Skills Hub 集成 - GitHub/skills.sh 技能发现
7. Trust Levels - builtin/trusted/community 分级

使用方法:
    from src.tools.skill_loader import SkillLoader, load_skill

    loader = SkillLoader()
    content = loader.load_skill_content("my-skill")

    # Skills Hub
    from src.tools.skill_loader import skills_hub_list, skills_hub_install
    skills_hub_list()  # 发现社区技能
    skills_hub_install("example-skill")  # 安装技能
"""

# 主类
# API 函数
from ._api import (
    _global_loader,
    _set_global_loader,
    get_loader,
    list_skills,
    load_skill,
    register_skill_tools,
    search_skill,
)

# 缓存
from ._cache import SkillContentCache

# 配置
from ._config import MAX_LOADED_SKILL_CACHE, MEMORY_GRAPH_CONFIG, PLATFORM_MAP

# Wiki 知识落地 P2: Skills Hub 集成 (Hermes-Agent)
from ._hub import (
    GitHubSource,
    HubSearchResult,
    HubSkillInfo,
    SkillsHub,
    SkillSource,
    SkillSourceType,
    TrustLevel,
    WellKnownSkillSource,
    skills_hub_install,
    skills_hub_installed,
    skills_hub_list,
    skills_hub_search,
    skills_hub_uninstall,
)

# 加载器函数
from ._loader import get_gene_slice, load_skill_content
from ._skillloader import SkillLoader

# 类型
from ._types import SkillMeta, SkillMetadata

# 磁盘缓存
from .skill_cache import (
    SNAPSHOT_PATH,
    build_manifest,
    clear_snapshot,
    load_snapshot,
    save_snapshot,
)

# 安全
from .skill_security import (
    INJECTION_PATTERNS,
    scan_for_injections,
    validate_path_within_dir,
    validate_skill_structure,
)

# 兼容别名
_get_loader = get_loader
_build_manifest = build_manifest  # 内部函数兼容别名
_scan_for_injections = scan_for_injections  # 内部函数兼容别名
_validate_skill_structure = validate_skill_structure  # 内部函数兼容别名


__all__ = [
    "INJECTION_PATTERNS",
    "MAX_LOADED_SKILL_CACHE",
    "MEMORY_GRAPH_CONFIG",
    "PLATFORM_MAP",
    "SNAPSHOT_PATH",
    "GitHubSource",
    "HubSearchResult",
    "HubSkillInfo",
    "SkillContentCache",
    "SkillLoader",
    "SkillMeta",
    "SkillMetadata",
    "SkillSource",
    "SkillSourceType",
    "SkillsHub",
    # Wiki 知识落地 P2: Skills Hub
    "TrustLevel",
    "WellKnownSkillSource",
    "_build_manifest",
    "_get_loader",
    "_global_loader",
    "_scan_for_injections",
    "_set_global_loader",
    "_validate_skill_structure",
    "build_manifest",
    "clear_snapshot",
    "get_gene_slice",
    "get_loader",
    "list_skills",
    "load_skill",
    "load_skill_content",
    "load_snapshot",
    "register_skill_tools",
    "save_snapshot",
    "scan_for_injections",
    "search_skill",
    "skills_hub_install",
    "skills_hub_installed",
    "skills_hub_list",
    "skills_hub_search",
    "skills_hub_uninstall",
    "validate_path_within_dir",
    "validate_skill_structure",
]