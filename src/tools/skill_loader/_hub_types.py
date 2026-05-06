"""Skills Hub 枚举和数据类型

Wiki 知识落地 P2 (Hermes-Agent): Skills Hub 集成
"""

from dataclasses import dataclass, field
from enum import Enum


class TrustLevel(Enum):
    """技能信任级别

    Hermes-Agent Trust Levels:
    - builtin: 内置技能，最高信任
    - trusted: 来自可信仓库
    - community: 来自社区，需要安全扫描
    """

    BUILTIN = "builtin"
    TRUSTED = "trusted"
    COMMUNITY = "community"


class SkillSourceType(Enum):
    """技能来源类型"""

    GITHUB = "github"
    WELL_KNOWN = "well_known"
    LOCAL = "local"


@dataclass
class HubSkillInfo:
    """Hub 技能信息

    包含技能的元数据和来源信息。
    """

    name: str
    description: str
    source: SkillSourceType
    source_url: str
    trust_level: TrustLevel
    version: str = "latest"
    category: str = ""
    platforms: list[str] = field(default_factory=list)
    install_path: str = ""


@dataclass
class HubSearchResult:
    """Hub 搜索结果"""

    total: int
    skills: list[HubSkillInfo]
    page: int = 1
    per_page: int = 20
    error: str | None = None


__all__ = [
    "TrustLevel",
    "SkillSourceType",
    "HubSkillInfo",
    "HubSearchResult",
]