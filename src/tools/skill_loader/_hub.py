"""
Skills Hub 集成模块 (Wiki 知识落地 P2: Hermes-Agent)

基于 Hermes-Agent Skills Hub 设计：
- GitHubSource: 从 GitHub 仓库获取技能
- WellKnownSkillSource: 从域名获取技能（/.well-known/skills/index.json）
- SkillsHub: 协调多个 Source 的统一接口
- Trust Levels: builtin, trusted, community

核心功能：
- skills_hub_list: 列出可用技能（社区发现）
- skills_hub_install: 安装技能到本地
- skills_hub_search: 搜索技能

使用场景：
- 发现社区技能
- 安装第三方技能
- 技能仓库管理
"""

import asyncio
import json
import logging
import os
import re
import shutil
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# 枚举和数据类型
# ============================================================================


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


# ============================================================================
# SkillSource 抽象接口
# ============================================================================


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


# ============================================================================
# GitHub Source
# ============================================================================


# 默认 GitHub 仓库配置
DEFAULT_GITHUB_TAPS = [
    {"repo": "openai/skills", "path": "skills/"},
    {"repo": "anthropics/skills", "path": "skills/"},
    {"repo": "VoltAgent/awesome-agent-skills", "path": "skills/"},
]


class GitHubSource(SkillSource):
    """GitHub 仓库技能来源

    通过 GitHub Contents API 获取技能列表和内容。
    """

    def __init__(self, taps: list[dict[str, str]] | None = None):
        """初始化

        Args:
            taps: GitHub 仓库配置列表
                  [{"repo": "owner/repo", "path": "skills/"}]
        """
        self._taps = taps or DEFAULT_GITHUB_TAPS
        self._cache: dict[str, list[HubSkillInfo]] = {}
        self._cache_time: dict[str, datetime] = {}

    @property
    def source_type(self) -> SkillSourceType:
        return SkillSourceType.GITHUB

    def is_available(self) -> bool:
        """检查 GitHub API 是否可达"""
        try:
            req = urllib.request.Request(
                "https://api.github.com",
                headers={"User-Agent": "seed-agent-skills-hub"},
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status == 200
        except Exception:
            return False

    async def list_skills(self) -> list[HubSkillInfo]:
        """列出所有 GitHub 仓库中的技能"""
        skills = []
        for tap in self._taps:
            repo_skills = await self._fetch_repo_skills(tap)
            skills.extend(repo_skills)
        return skills

    async def search_skills(self, query: str, limit: int = 20) -> list[HubSkillInfo]:
        """搜索 GitHub 仓库中的技能"""
        all_skills = await self.list_skills()
        query_lower = query.lower()

        matched = []
        for skill in all_skills:
            # 匹配名称、描述、类别
            if query_lower in skill.name.lower():
                matched.append(skill)
            elif query_lower in skill.description.lower():
                matched.append(skill)
            elif query_lower in skill.category.lower():
                matched.append(skill)

        return matched[:limit]

    async def install_skill(
        self, skill_info: HubSkillInfo, target_path: Path, force: bool = False
    ) -> str:
        """从 GitHub 安装技能"""
        if target_path.exists() and not force:
            return f"Skill already installed: {target_path}"

        try:
            # 下载 SKILL.md
            skill_url = skill_info.source_url
            content = await self._fetch_github_content(skill_url)

            # 创建目录
            skill_dir = target_path / skill_info.name
            skill_dir.mkdir(parents=True, exist_ok=True)

            # 写入 SKILL.md
            skill_file = skill_dir / "SKILL.md"
            with open(skill_file, "w", encoding="utf-8") as f:
                f.write(content)

            # 记录来源信息
            lock_file = skill_dir / ".hub-lock.json"
            lock_data = {
                "source": skill_info.source.value,
                "source_url": skill_info.source_url,
                "trust_level": skill_info.trust_level.value,
                "installed_at": datetime.now().isoformat(),
                "version": skill_info.version,
            }
            with open(lock_file, "w", encoding="utf-8") as f:
                json.dump(lock_data, f, indent=2)

            return f"Installed skill: {skill_info.name} ({skill_info.trust_level.value})"

        except Exception as e:
            return f"Error installing skill: {type(e).__name__}: {str(e)[:100]}"

    async def _fetch_repo_skills(self, tap: dict[str, str]) -> list[HubSkillInfo]:
        """获取指定仓库的技能列表"""
        repo = tap["repo"]
        path = tap["path"]
        cache_key = f"{repo}:{path}"

        # 检查缓存（1小时有效期）
        if cache_key in self._cache:
            cache_time = self._cache_time.get(cache_key)
            if cache_time and (datetime.now() - cache_time).total_seconds() < 3600:
                return self._cache[cache_key]

        skills = []
        try:
            # GitHub Contents API
            api_url = f"https://api.github.com/repos/{repo}/contents/{path}"
            req = urllib.request.Request(
                api_url,
                headers={"User-Agent": "seed-agent-skills-hub"},
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

            # 遍历目录
            for item in data:
                if item.get("type") == "dir":
                    skill_name = item.get("name", "")
                    if skill_name:
                        skill_url = f"https://raw.githubusercontent.com/{repo}/main/{path}{skill_name}/SKILL.md"
                        skills.append(
                            HubSkillInfo(
                                name=skill_name,
                                description=f"Skill from {repo}",
                                source=self.source_type,
                                source_url=skill_url,
                                trust_level=self.determine_trust_level(repo),
                            )
                        )

            # 更新缓存
            self._cache[cache_key] = skills
            self._cache_time[cache_key] = datetime.now()

        except Exception as e:
            logger.warning(f"Failed to fetch skills from {repo}: {type(e).__name__}")

        return skills

    async def _fetch_github_content(self, url: str) -> str:
        """获取 GitHub 文件内容"""
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "seed-agent-skills-hub"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode()


# ============================================================================
# Well-Known Source
# ============================================================================


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


# ============================================================================
# SkillsHub 协调器
# ============================================================================


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


# ============================================================================
# 公共 API 工具函数
# ============================================================================


def skills_hub_list(refresh: bool = False) -> str:
    """列出 Hub 中所有可用技能（同步版本）

    Args:
        refresh: 是否刷新缓存

    Returns:
        技能列表字符串
    """
    hub = SkillsHub()

    async def _list():
        result = await hub.discover_skills(refresh)
        lines = [
            f"Total: {result.total} skills available",
            "",
        ]
        if result.error:
            lines.append(f"Warnings: {result.error}")
            lines.append("")

        for skill in result.skills:
            lines.append(
                f"- [{skill.trust_level.value}] {skill.name}: {skill.description[:50]}..."
            )

        return "\n".join(lines)

    return asyncio.run(_list())


def skills_hub_search(query: str, limit: int = 10) -> str:
    """搜索 Hub 中的技能（同步版本）

    Args:
        query: 搜索关键词
        limit: 最大结果数

    Returns:
        搜索结果字符串
    """
    hub = SkillsHub()

    async def _search():
        result = await hub.search_skills(query, limit)
        lines = [
            f"Search: '{query}' - Found {result.total} skills",
            "",
        ]

        for skill in result.skills:
            lines.append(
                f"- [{skill.trust_level.value}] {skill.name}"
            )
            lines.append(f"  Source: {skill.source.value}")
            lines.append(f"  Description: {skill.description[:100]}...")
            lines.append("")

        return "\n".join(lines)

    return asyncio.run(_search())


def skills_hub_install(skill_name: str, force: bool = False) -> str:
    """安装 Hub 中的技能（同步版本）

    Args:
        skill_name: 技能名称
        force: 是否强制覆盖

    Returns:
        安装结果字符串
    """
    hub = SkillsHub()

    async def _install():
        return await hub.install_skill(skill_name, force=force)

    return asyncio.run(_install())


def skills_hub_uninstall(skill_name: str) -> str:
    """卸载已安装的技能

    Args:
        skill_name: 技能名称

    Returns:
        卸载结果字符串
    """
    hub = SkillsHub()
    return hub.uninstall_skill(skill_name)


def skills_hub_installed() -> str:
    """列出已安装的技能

    Returns:
        已安装技能列表字符串
    """
    hub = SkillsHub()
    installed = hub.list_installed_skills()

    if not installed:
        return "No skills installed from Hub."

    lines = ["Installed skills:", ""]
    for skill in installed:
        trust = skill.get("trust_level", "unknown")
        source = skill.get("source", "unknown")
        lines.append(f"- [{trust}] {skill['name']} (from {source})")

    return "\n".join(lines)


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