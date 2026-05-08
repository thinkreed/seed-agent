"""SkillsHub 协调器

Wiki 知识落地 P2 (Hermes-Agent): Skills Hub 集成

聚合发现、搜索、安装、管理功能。
"""

import logging
from pathlib import Path

from ._hub_discovery import SkillsHubDiscovery
from ._hub_github import GitHubSource
from ._hub_management import SkillsHubManagement
from ._hub_types import HubSearchResult, TrustLevel

logger = logging.getLogger(__name__)


class SkillsHub:
    """Skills Hub 协调器

    协调多个技能来源，提供统一的发现、搜索、安装接口。
    """

    def __init__(self, skills_dir: Path | None = None):
        """初始化

        Args:
            skills_dir: 本地技能目录（默认 ~/.seed/memory/skills）
        """
        self._skills_dir = skills_dir or self._get_default_skills_dir()
        self._hub_dir = self._skills_dir / ".hub"

        # 初始化子组件
        self._discovery = SkillsHubDiscovery()
        self._management = SkillsHubManagement(self._skills_dir)

        # 创建 .hub 目录
        self._hub_dir.mkdir(parents=True, exist_ok=True)

    def _get_default_skills_dir(self) -> Path:
        """获取默认技能目录"""
        try:
            from src.shared_config import get_paths_config
            return get_paths_config().memory_dir / "skills"
        except RuntimeError:
            return Path.home() / ".seed" / "memory" / "skills"

    # === 发现接口 ===

    async def discover_skills(self, refresh: bool = False) -> HubSearchResult:
        """发现所有可用技能"""
        return await self._discovery.discover_skills(refresh)

    async def search_skills(self, query: str, limit: int = 20) -> HubSearchResult:
        """搜索技能"""
        return await self._discovery.search_skills(query, limit)

    async def install_skill(
        self,
        skill_name: str,
        trust_level: TrustLevel | None = None,
        force: bool = False,
    ) -> str:
        """安装技能"""
        return await self._discovery.install_skill(
            skill_name, trust_level, force, self._skills_dir
        )

    # === 管理接口 ===

    def list_installed_skills(self) -> list[dict]:
        """列出已安装的技能"""
        return self._management.list_installed_skills()

    def uninstall_skill(self, skill_name: str) -> str:
        """卸载技能"""
        return self._management.uninstall_skill(skill_name)


__all__ = ["SkillsHub"]