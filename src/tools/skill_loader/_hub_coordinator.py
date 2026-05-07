"""SkillsHub 协调器

Wiki 知识落地 P2 (Hermes-Agent): Skills Hub 集成
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from ._hub_github import GitHubSource
from ._hub_source import SkillSource
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
        self._sources: list[SkillSource] = []
        self._hub_dir = self._skills_dir / ".hub"

        # 初始化默认来源
        self._sources.append(GitHubSource())

        # 创建 .hub 目录
        self._hub_dir.mkdir(parents=True, exist_ok=True)

    def _get_default_skills_dir(self) -> Path:
        """获取默认技能目录"""
        try:
            from src.shared_config import get_paths_config
            return get_paths_config().memory_dir / "skills"
        except RuntimeError:
            return Path.home() / ".seed" / "memory" / "skills"

    def add_source(self, source: SkillSource) -> None:
        """添加技能来源"""
        self._sources.append(source)

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
    ) -> str:
        """安装技能

        Args:
            skill_name: 技能名称
            trust_level: 期望的信任级别
            force: 是否强制覆盖

        Returns:
            安装结果消息
        """
        # 搜索技能
        result = await self.search_skills(skill_name, limit=5)

        if not result.skills:
            return f"Skill not found: {skill_name}"

        # 选择最佳匹配
        best_match = result.skills[0]

        # 检查信任级别
        if trust_level and best_match.trust_level != trust_level:
            # 尝试找到匹配信任级别的版本
            for skill in result.skills:
                if skill.trust_level == trust_level:
                    best_match = skill
                    break

        # 执行安装
        for source in self._sources:
            if source.source_type == best_match.source:
                return await source.install_skill(
                    best_match, self._skills_dir, force
                )

        return f"No installer available for {skill_name}"

    def list_installed_skills(self) -> list[dict[str, Any]]:
        """列出已安装的技能"""
        installed = []

        if not self._skills_dir.exists():
            return installed

        for skill_dir in self._skills_dir.iterdir():
            if skill_dir.is_dir() and skill_dir.name != ".hub":
                skill_file = skill_dir / "SKILL.md"
                lock_file = skill_dir / ".hub-lock.json"

                info = {
                    "name": skill_dir.name,
                    "installed": skill_file.exists(),
                }

                if lock_file.exists():
                    try:
                        with open(lock_file, encoding="utf-8") as f:
                            lock_data = json.load(f)
                        info.update(lock_data)
                    except Exception:
                        pass

                installed.append(info)

        return installed

    def uninstall_skill(self, skill_name: str) -> str:
        """卸载技能"""
        skill_dir = self._skills_dir / skill_name

        if not skill_dir.exists():
            return f"Skill not installed: {skill_name}"

        try:
            shutil.rmtree(skill_dir)
            return f"Uninstalled skill: {skill_name}"
        except Exception as e:
            return f"Error uninstalling skill: {type(e).__name__}: {str(e)[:100]}"


__all__ = ["SkillsHub"]