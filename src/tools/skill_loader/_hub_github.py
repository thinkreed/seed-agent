"""GitHub 仓库技能来源

Wiki 知识落地 P2 (Hermes-Agent): Skills Hub 集成
"""

import json
import logging
import urllib.request
from datetime import datetime
from pathlib import Path

from ._hub_source import SkillSource
from ._hub_types import HubSkillInfo, SkillSourceType

logger = logging.getLogger(__name__)


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
            if query_lower in skill.name.lower() or query_lower in skill.description.lower() or query_lower in skill.category.lower():
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


__all__ = ["DEFAULT_GITHUB_TAPS", "GitHubSource"]