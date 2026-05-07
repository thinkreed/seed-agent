"""Well-Known 技能来源

Wiki 知识落地 P2 (Hermes-Agent): Skills Hub 集成
"""

import json
import logging
import urllib.request
from pathlib import Path

from ._hub_source import SkillSource
from ._hub_types import HubSkillInfo, SkillSourceType, TrustLevel

logger = logging.getLogger(__name__)


class WellKnownSkillSource(SkillSource):
    """/.well-known/skills 技能来源

    从域名获取技能列表（/.well-known/skills/index.json）。
    """

    def __init__(self, domains: list[str] | None = None):
        """初始化

        Args:
            domains: 要检查的域名列表
        """
        self._domains = domains or []

    @property
    def source_type(self) -> SkillSourceType:
        return SkillSourceType.WELL_KNOWN

    def is_available(self) -> bool:
        return len(self._domains) > 0

    async def list_skills(self) -> list[HubSkillInfo]:
        """列出所有域名的技能"""
        skills = []
        for domain in self._domains:
            domain_skills = await self._fetch_domain_skills(domain)
            skills.extend(domain_skills)
        return skills

    async def search_skills(self, query: str, limit: int = 20) -> list[HubSkillInfo]:
        """搜索域名中的技能"""
        all_skills = await self.list_skills()
        query_lower = query.lower()

        matched = [
            s
            for s in all_skills
            if query_lower in s.name.lower() or query_lower in s.description.lower()
        ]
        return matched[:limit]

    async def install_skill(
        self, skill_info: HubSkillInfo, target_path: Path, force: bool = False
    ) -> str:
        """从域名安装技能"""
        # 实现类似 GitHubSource
        return f"Not implemented for well-known source: {skill_info.name}"

    async def _fetch_domain_skills(self, domain: str) -> list[HubSkillInfo]:
        """获取指定域名的技能列表"""
        skills = []
        try:
            url = f"https://{domain}/.well-known/skills/index.json"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

            # 解析技能列表
            for skill_data in data.get("skills", []):
                skills.append(
                    HubSkillInfo(
                        name=skill_data.get("name", ""),
                        description=skill_data.get("description", ""),
                        source=self.source_type,
                        source_url=f"https://{domain}/skills/{skill_data.get('name', '')}",
                        trust_level=TrustLevel.TRUSTED,
                    )
                )

        except Exception as e:
            logger.warning(f"Failed to fetch skills from {domain}: {type(e).__name__}")

        return skills


__all__ = ["WellKnownSkillSource"]