"""
Skill 索引渲染模块

提供 Skill 索引生成和分类渲染功能。
"""


def render_category(cat: str, skills: list[dict], indent: bool = False) -> list[str]:
    """渲染分类区块

    Args:
        cat: 分类名称
        skills: Skill 元数据列表
        indent: 是否缩进

    Returns:
        渲染后的行列表
    """
    prefix = "  - " if indent else "- "
    lines = [f"<category name='{cat}'>"]
    for meta in skills:
        lines.append(f"{prefix}**{meta['name']}**: {meta['description'][:150]}")
    lines.extend(["</category>", ""])
    return lines


def build_skills_index(
    skills_meta: dict,
    should_show_fn: callable,
    available_tools: set[str] | None = None,
) -> str:
    """构建 Tier 1 索引

    Args:
        skills_meta: Skill 元数据字典
        should_show_fn: 条件激活判断函数
        available_tools: 可用工具集合

    Returns:
        索引字符串
    """
    visible = {n: m for n, m in skills_meta.items() if should_show_fn(n, available_tools)}
    if not visible:
        return ""

    categories: dict[str, list[dict]] = {}
    for meta in visible.values():
        categories.setdefault(meta.get("category", "general"), []).append(meta)

    lines = ["<skills_index>", "## 可用技能", "", "触发词匹配时调用 `load_skill` 加载完整指令。", ""]
    if "general" in categories:
        lines.extend(render_category("general", categories.pop("general")))
    for cat, skills in sorted(categories.items()):
        lines.extend(render_category(cat, skills, indent=True))
    lines.append("</skills_index>")
    return "\n".join(lines)


__all__ = [
    "render_category",
    "build_skills_index",
]