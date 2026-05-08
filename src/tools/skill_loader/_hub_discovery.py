"""SkillsHub 发现和搜索功能

提取 discover_skills, search_skills, install_skill 方法。
"""

import logging
from pathlib import Path
from typing import Any

from ._hub_github import GitHubSource
from ._hub_source import SkillSource
from ._hub_types import HubSearchResult, TrustLevel

logger = logging.getLogger(__name__)


class SkillsHubDiscovery:
    """Skills Hub 发现和搜索协调器"""

    def __init__(self, sources: list[SkillSource] | None = None):
        """初始化

        Args:
            sources: 技能来源列表
        """
        self._sources = sources or [GitHubSource()]

    async def discover_skills(self, refresh: bool = False) -> HubSearchResult:
        """发现所有可用技能

        Args:
            refresh: 是否刷新缓存

        Returns:
            HubSearchResult: 搜索结果
        """
        skills = []
        errors = []

        for source in self._sources:
            if not source.is_available():
                errors.append(f"Source {source.source_type.value} not available")
                continue

            try:
                source_skills = await source.list_skills()
                skills.extend(source_skills)
            except Exception as e:
                errors.append(f"Source {source.source_type.value}: {type(e).__name__}")

        return HubSearchResult(
            total=len(skills),
            skills=skills,
            error="; ".join(errors) if errors else None,
        )

    async def search_skills(self, query: str, limit: int = 20) -> HubSearchResult:
        """搜索技能

        Args:
            query: 搜索关键词
            limit: 最大结果数

        Returns:
            HubSearchResult: 搜索结果
        """
        skills = []

        for source in self._sources:
            if source.is_available():
                try:
                    source_skills = await source.search_skills(query, limit)
                    skills.extend(source_skills)
                except Exception as e:
                    logger.warning(f"Search failed for {source.source_type.value}: {e}")

        return HubSearchResult(
            total=len(skills),
            skills=skills[:limit],
        )

    async def install_skill(
        self,
        skill_name: str,
        trust_level: TrustLevel | None = None,
        force: bool = False,
        skills_dir: Path | None = None,
    ) -> str:
        """安装技能

        Args:
            skill_name: 技能名称
            trust_level: 期望的信任级别
            force: 是否强制覆盖
            skills_dir: 目标目录

        Returns:
            安装结果消息
        """
        result = await self.search_skills(skill_name, limit=5)

        if not result.skills:
            return f"Skill not found: {skill_name}"

        best_match = result.skills[0]

        if trust_level and best_match.trust_level != trust_level:
            for skill in result.skills:
                if skill.trust_level == trust_level:
                    best_match = skill
                    break

        for source in self._sources:
            if source.source_type == best_match.source:
                return await source.install_skill(best_match, skills_dir, force)

        return f"No installer available for {skill_name}"


__all__ = ["SkillsHubDiscovery"]