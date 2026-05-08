"""Prompt 构建辅助模块

从 executor_task.py 提取的 prompt 构建逻辑。
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agent_loop import AgentLoop

from src.autonomous._prompt_builder import build_autonomous_prompt, extract_task_signals
from src.autonomous._sop_loader import expand_sop_paths

logger = logging.getLogger("seed_agent")


def build_full_prompt(
    agent: "AgentLoop", sop_content: str | None, todo_content: str, seed_dir: Path
) -> str:
    """构建完整的自主探索 prompt

    Args:
        agent: AgentLoop 实例
        sop_content: SOP 内容
        todo_content: TODO 内容
        seed_dir: Seed 目录

    Returns:
        完整的自主探索 prompt
    """
    base_system_prompt = agent.system_prompt or ""

    skills_prompt = ""
    best_skill = None
    gene_slice = None

    skill_loader = getattr(agent, "skill_loader", None)
    if skill_loader:
        skills_prompt = skill_loader.get_skills_prompt()
        signals = extract_task_signals(todo_content, bool(todo_content))
        best_skill = skill_loader.select_best_skill(
            signals=signals,
            available_tools=getattr(agent.tools, "get_tool_names", lambda: None)(),
        )
        if best_skill:
            gene_slice = skill_loader.get_gene_slice(best_skill)

    expanded_sop = expand_sop_paths(sop_content or "", seed_dir)

    return build_autonomous_prompt(
        base_system_prompt=base_system_prompt,
        skills_prompt=skills_prompt,
        sop_content=expanded_sop,
        todo_content=todo_content,
        has_todo=bool(todo_content),
        seed_dir=seed_dir,
        best_skill=best_skill,
        gene_slice=gene_slice,
    )


__all__ = ["build_full_prompt"]