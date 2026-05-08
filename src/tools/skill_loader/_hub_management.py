"""SkillsHub 管理功能

提取 list_installed_skills, uninstall_skill 方法。
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SkillsHubManagement:
    """Skills Hub 管理器"""

    def __init__(self, skills_dir: Path):
        """初始化

        Args:
            skills_dir: 本地技能目录
        """
        self._skills_dir = skills_dir

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


__all__ = ["SkillsHubManagement"]