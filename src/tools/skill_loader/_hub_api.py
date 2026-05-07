"""Skills Hub 公共 API 函数

Wiki 知识落地 P2 (Hermes-Agent): Skills Hub 集成
"""

import asyncio

from ._hub_coordinator import SkillsHub


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
    "skills_hub_install",
    "skills_hub_installed",
    "skills_hub_list",
    "skills_hub_search",
    "skills_hub_uninstall",
]