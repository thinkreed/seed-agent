"""Skills Hub 集成模块入口 (Wiki 知识落地 P2: Hermes-Agent)

模块拆分：
- _hub_types.py: 枚举和数据类型
- _hub_source.py: SkillSource 抽象接口
- _hub_github.py: GitHub 仓库技能来源
- _hub_wellknown.py: Well-Known 技能来源
- _hub_coordinator.py: SkillsHub 协调器
- _hub_api.py: 公共 API 工具函数

核心功能：
- skills_hub_list: 列出可用技能（社区发现）
- skills_hub_install: 安装技能到本地
- skills_hub_search: 搜索技能
"""

# 导入所有模块
from ._hub_types import (
    TrustLevel,
    SkillSourceType,
    HubSkillInfo,
    HubSearchResult,
)
from ._hub_source import SkillSource
from ._hub_github import GitHubSource, DEFAULT_GITHUB_TAPS
from ._hub_wellknown import WellKnownSkillSource
from ._hub_coordinator import SkillsHub
from ._hub_api import (
    skills_hub_list,
    skills_hub_search,
    skills_hub_install,
    skills_hub_uninstall,
    skills_hub_installed,
)


__all__ = [
    # 枚举和类型
    "TrustLevel",
    "SkillSourceType",
    "HubSkillInfo",
    "HubSearchResult",
    # 来源类
    "SkillSource",
    "GitHubSource",
    "WellKnownSkillSource",
    # 协调器
    "SkillsHub",
    # 公共 API
    "skills_hub_list",
    "skills_hub_search",
    "skills_hub_install",
    "skills_hub_uninstall",
    "skills_hub_installed",
]