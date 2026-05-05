"""
Skill Loader API 模块

提供全局单例和便捷函数。
"""

import threading
from typing import TYPE_CHECKING

from ._loader import get_gene_slice, load_skill_content

if TYPE_CHECKING:
    from ._types import SkillMeta
    from src.tools import ToolRegistry

# === 全局单例 ===

_global_loader: "SkillLoader | None" = None
_loader_lock = threading.Lock()


def _set_global_loader(loader: "SkillLoader | None") -> None:
    """设置全局 loader（用于测试）"""
    global _global_loader
    _global_loader = loader


def get_loader() -> "SkillLoader":
    """获取全局 loader"""
    global _global_loader
    if _global_loader is None:
        with _loader_lock:
            if _global_loader is None:
                # 延迟导入避免循环依赖
                from . import SkillLoader
                _global_loader = SkillLoader()
    return _global_loader


def load_skill(name: str) -> str:
    """加载 skill 内容"""
    loader = get_loader()
    content = loader.load_skill_content(name)
    if content:
        return f'[SYSTEM: Skill "{name}" activated]\n\n{content}'
    return f"Skill not found: {name}. Available: {', '.join(loader.get_skill_names())}"


def list_skills() -> str:
    """列出所有 skills"""
    loader = get_loader()
    skills = list(loader._skills_meta.values())
    if not skills:
        return "No skills available."

    categories: dict[str, list[dict]] = {}
    for s in skills:
        categories.setdefault(s.get("category", "general"), []).append(s)

    output = "Available Skills:\n"
    for cat, items in sorted(categories.items()):
        output += f"\n  [{cat}]\n"
        for s in items:
            output += f"  - {s['name']}: {s.get('description', '')[:100]}\n"
    return output


def search_skill(query: str) -> str:
    """搜索 skill"""
    loader = get_loader()
    match = loader.match_skill(query)

    if match:
        content = loader.load_skill_content(match)
        if content:
            return f"[Matched] {match}\n\n{content}"

    query_lower = query.lower()
    candidates = [
        f"- {n}: {m['description'][:100]}"
        for n, m in loader._skills_meta.items()
        if query_lower in n.lower() or query_lower in m["description"].lower()
    ]

    if candidates:
        return "No exact match. Candidates:\n" + "\n".join(candidates)
    return f"No skill matches: {query}"


def register_skill_tools(registry: "ToolRegistry") -> None:
    """注册 skill 工具"""
    registry.register("load_skill", load_skill)
    registry.register("list_skills", list_skills)
    registry.register("search_skill", search_skill)


_get_loader = get_loader  # 兼容别名


__all__ = [
    "get_loader",
    "_get_loader",
    "load_skill",
    "list_skills",
    "search_skill",
    "register_skill_tools",
]