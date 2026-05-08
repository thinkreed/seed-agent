"""Prompt 构建模块

提供自主探索 Prompt 构建功能:
- build_autonomous_prompt: 构建完整的自主探索 prompt
- build_task_instruction: 构建任务指令部分

从 AutonomousExplorer 中提取，保持接口不变。
"""

import logging
import os
from pathlib import Path

from src.autonomous._prompt_extraction import (
    extract_autonomous_prompt_core,
    extract_task_signals,
)
from src.autonomous._sop_loader import get_project_root

logger = logging.getLogger("seed_agent")


def build_autonomous_prompt(
    base_system_prompt: str,
    skills_prompt: str,
    sop_content: str,
    todo_content: str,
    has_todo: bool,
    seed_dir: Path,
    best_skill: str | None = None,
    gene_slice: str | None = None,
) -> str:
    """构建自主探索 prompt（包含完整 system prompt + skills + SOP + Memory Graph 选择）

    Args:
        base_system_prompt: Agent 的基础 system prompt
        skills_prompt: Skills prompt
        sop_content: SOP 内容（已展开路径）
        todo_content: TODO 文件内容
        has_todo: 是否有 TODO
        seed_dir: 主工作目录路径
        best_skill: Memory Graph 推荐的最佳 skill
        gene_slice: 推荐 skill 的 Gene slice

    Returns:
        完整的自主探索 prompt
    """
    # 构建推荐技能部分
    best_skill_suggestion = ""
    if best_skill and gene_slice:
        best_skill_suggestion = f"""## 推荐技能 (Memory Graph 选择)

基于历史成功率，推荐使用技能: **{best_skill}**

{gene_slice}

"""
        logger.info(f"Memory Graph selected skill: {best_skill}")

    # 构建 SOP 内容
    sop_prompt = f"""## 自主探索 SOP

{sop_content}

"""

    # 构建任务指令
    task_prompt = build_task_instruction(todo_content, has_todo, seed_dir)

    # 组合完整 prompt
    parts = []
    if base_system_prompt:
        parts.append(base_system_prompt)
    if skills_prompt and skills_prompt not in base_system_prompt:
        parts.append(skills_prompt)
    if best_skill_suggestion:
        parts.append(best_skill_suggestion)
    parts.append(sop_prompt)
    parts.append(task_prompt)

    return "\n\n".join(parts)


def build_task_instruction(
    todo_content: str,
    has_todo: bool,
    seed_dir: Path,
) -> str:
    """构建任务指令部分

    Args:
        todo_content: TODO 文件内容
        has_todo: 是否有 TODO
        seed_dir: 主工作目录路径

    Returns:
        任务指令字符串
    """
    project_root = get_project_root()
    seed_dir_absolute = str(seed_dir)
    project_root_absolute = str(project_root)

    prompt_parts = [
        "# 自主探索任务触发",
        "",
        "当前空闲2小时，开始执行自主任务。",
        "",
        "## 当前状态",
        f"- TODO状态: {'有待执行任务' if has_todo else '无TODO，进入规划模式'}",
        f"- 工作目录: {seed_dir_absolute}",
        "",
        "## 重要路径说明（使用绝对路径）",
        "",
        "### 记忆系统路径（位于用户目录）",
        f"- 记忆目录: {os.path.join(seed_dir_absolute, 'memory')}",
        f"- Skills目录: {os.path.join(seed_dir_absolute, 'memory', 'skills')}",
        f"- TODO文件: {os.path.join(seed_dir_absolute, 'TODO.md')}",
        f"- 日志目录: {os.path.join(seed_dir_absolute, 'logs')}",
        "",
        "### 项目源码路径（位于项目目录）",
        f"- 项目根目录: {project_root_absolute}",
        f"- 源码目录: {os.path.join(project_root_absolute, 'src')}",
        f"- Agent模块: {os.path.join(project_root_absolute, 'src', 'agent_loop.py')}",
        f"- LLM Gateway: {os.path.join(project_root_absolute, 'src', 'client.py')}",
        f"- 工具模块: {os.path.join(project_root_absolute, 'src', 'tools')}",
        "",
        "**关键提示**: ",
        "1. 记忆系统文件（Skills、TODO等）使用 `.seed` 目录下的绝对路径",
        "2. 项目源码文件（src/*.py）使用项目目录下的绝对路径",
        f"3. 不要混淆两者：`src/client.py` 应为 `{os.path.join(project_root_absolute, 'src', 'client.py')}`，"
        f"而非 `{os.path.join(seed_dir_absolute, 'src', 'client.py')}`",
        "",
    ]

    if has_todo and todo_content.strip():
        prompt_parts.extend(
            [
                "## 当前TODO内容",
                todo_content,
                "",
                "请按照 SOP 执行流程，逐个完成 TODO 条目：",
                "1. 在 <thinking> 内推演执行逻辑",
                "2. 执行任务并记录到工作记忆",
                "3. 完成后标记 TODO 并更新工作记忆",
                "",
            ]
        )
    else:
        prompt_parts.extend(
            [
                "## 规划模式",
                "当前无TODO，请进入规划模式：",
                "1. 读取 history.md 和工作记忆",
                "2. 反思低价值操作，提炼进化线索",
                "3. 产出5-7条TODO（格式：`[ ] 类型 | 目标 | 验收标准 | 预期沉淀`）",
                "4. 更新 TODO.md 文件",
                "",
            ]
        )

    prompt_parts.extend(
        [
            "## SOP 核心原则",
            "- 价值公式：实际执行可落地性 × 进化沉淀价值",
            "- 不推诿、有逻辑、重沉淀",
            "- 失败升级：1次重试，2次探测，3次换方案",
            "- 不可逆操作需先确认用户（但自主模式下跳过需确认的操作）",
            "",
            "请开始执行自主探索任务。",
        ]
    )

    return "\n".join(prompt_parts)


# 导出提取函数以保持 API 兼容
__all__ = [
    "build_autonomous_prompt",
    "build_task_instruction",
    "extract_task_signals",
    "extract_autonomous_prompt_core",
]