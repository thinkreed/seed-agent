"""
记忆搜索和索引读取

核心功能：
- read_memory_index: 读取 L1 索引
- search_memory: 跨层级关键词搜索
- start_long_term_update: 任务完成触发经验提炼
"""

import logging
import os
from pathlib import Path

from ._memory_write import _get_memory_root, _get_path

logger = logging.getLogger(__name__)


def read_memory_index() -> str:
    """
    Read the global memory index (L1) to find available SOPs or knowledge.

    Returns:
        Content of notes.md or error message
    """
    path = _get_path("L1")
    if path is None or not os.path.exists(path):
        return "Memory index not found."
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading index: {e!s}"


def search_memory(keyword: str, levels: list[str] | None = None) -> str:
    """
    Search memory by keyword across L1/L2/L3.

    Args:
        keyword: Search keyword
        levels: Levels to search (default L1, L2, L3)

    Returns:
        List of matching files with levels.
    """
    if levels is None:
        levels = ["L1", "L2", "L3"]

    results = []
    memory_root = _get_memory_root()

    if not os.path.exists(memory_root):
        return "Memory root not found."

    for root, _, files in os.walk(memory_root):
        if ".git" in root or "__pycache__" in root:
            continue
        for file in files:
            if file.endswith((".md", ".txt")):
                # Determine level
                rel = os.path.relpath(root, memory_root)
                lvl = "Unknown"
                if "notes" in rel or file == "notes.md":
                    lvl = "L1"
                elif "skills" in rel:
                    lvl = "L2"
                elif "knowledge" in rel:
                    lvl = "L3"
                elif "raw" in rel:
                    lvl = "L4"

                if lvl in levels:
                    try:
                        fpath = os.path.join(root, file)
                        with open(fpath, encoding="utf-8", errors="ignore") as f:
                            if keyword.lower() in f.read().lower():
                                results.append(f"[{lvl}] {file}")
                    except Exception as e:
                        logger.debug(
                            f"Failed to read memory file {file}: {type(e).__name__}"
                        )
                        continue

    return "\n".join(results) if results else "No matching memory found."


def start_long_term_update(args: dict, **kwargs) -> str:
    """
    Triggered when the agent believes a task is complete.
    Dynamically reads memory SOP and injects it into the prompt.

    Args:
        args: 参数字典（包含可能的 task 信息）
        **kwargs: 其他参数

    Returns:
        经验提炼 SOP 指令
    """
    memory_md_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "memory", "memory.md"
    )
    sop_content = "[Error: Unable to load memory.md]"

    try:
        with open(memory_md_path, encoding="utf-8") as f:
            sop_content = f.read()
    except Exception as e:
        sop_content = f"Error reading SOP: {e!s}"

    return f"""### [经验提炼] 任务即将结束，请提炼并保存本次任务中的有效经验。

以下是必须严格遵守的记忆管理 SOP，请根据 SOP 中的层级定义和约束进行经验提炼：

{sop_content}

请总结以下内容并使用 `write_memory` 保存：
1. **环境事实/配置**: 经过验证的路径 (相对)、依赖、配置 (Level: L2)。
2. **SOP/技能**: 成功的操作步骤、代码片段、重试策略 (Level: L2)。
3. **避坑/知识**: 失败原因、解决方案、通用规则 (Level: L3)。
4. **用户偏好**: 特定的需求或习惯 (Level: L2)。"""