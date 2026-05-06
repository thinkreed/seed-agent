"""SkillSource 抽象接口

Wiki 知识落地 P2 (Hermes-Agent): Skills Hub 集成
"""

from abc import ABC, abstractmethod
from pathlib import Path

from ._hub_types import HubSkillInfo, SkillSourceType, TrustLevel


class SkillSource(ABC):
    """技能来源抽象接口

    定义了所有技能来源必须实现的方法。
    """

    @property
    @abstractmethod
    def source_type(self) -> SkillSourceType:
        """来源类型"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查来源是否可用"""
        pass

    @abstractmethod
    async def list_skills(self) -> list[HubSkillInfo]:
        """列出可用技能"""
        pass

    @abstractmethod
    async def search_skills(self, query: str, limit: int = 20) -> list[HubSkillInfo]:
        """搜索技能"""
        pass

    @abstractmethod
    async def install_skill(
        self, skill_info: HubSkillInfo, target_path: Path, force: bool = False
    ) -> str:
        """安装技能到目标路径"""
        pass

    def determine_trust_level(self, source_url: str) -> TrustLevel:
        """确定信任级别"""
        # 内置仓库
        builtin_repos = [
            "openai/skills",
            "anthropics/skills",
        ]
        for repo in builtin_repos:
            if repo in source_url:
                return TrustLevel.BUILTIN

        # 可信仓库
        trusted_repos = [
            "VoltAgent/awesome-agent-skills",
            "hermes-agent/skills",
        ]
        for repo in trusted_repos:
            if repo in source_url:
                return TrustLevel.TRUSTED

        return TrustLevel.COMMUNITY


__all__ = ["SkillSource"]