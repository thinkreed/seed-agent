"""Prompt 提取模块

提供自主探索 Prompt 提取功能:
- extract_task_signals: 从任务内容提取触发信号
- extract_autonomous_prompt_core: 提取 prompt 核心部分

从 _prompt_builder.py 拆分，保持接口不变。
"""

import re


def extract_task_signals(todo_content: str, has_todo: bool) -> list[str]:
    """从任务内容提取触发信号

    Args:
        todo_content: TODO 文件内容
        has_todo: 是否有 TODO

    Returns:
        触发信号列表（最多10个）
    """
    signals = []

    if has_todo and todo_content:
        # 从 TODO 内容提取关键词
        lines = todo_content.split("\n")
        for line in lines[:5]:
            # 提取 TODO 条目中的关键词
            if line.strip():
                words = line.split()
                signals.extend(words[:3])

    # 根据任务类型添加基础信号
    if has_todo:
        signals.append("execute")
        signals.append("task")
    else:
        signals.append("plan")
        signals.append("generate")

    return signals[:10]


def extract_autonomous_prompt_core(
    full_prompt: str,
    sop_content: str | None = None,
) -> str:
    """从完整自主探索 prompt 中提取核心指令部分（增强版）

    只保留 SOP 和任务指令，避免重复注入 skills（会导致上下文膨胀）。

    增强点：
    1. 如果提取失败，使用已加载的 SOP 作为 fallback
    2. 如果任务指令缺失，动态构建当前任务
    3. 确保始终返回有效内容（非空）

    Args:
        full_prompt: 完整的自主探索 prompt
        sop_content: 已加载的 SOP 内容（用于 fallback）

    Returns:
        提取的核心部分
    """
    # 匹配 SOP 部分
    sop_match = re.search(
        r"(##?\s*自主探索\s*SOP.*?)(?=##?\s*|$)",
        full_prompt,
        re.DOTALL | re.IGNORECASE,
    )
    extracted_sop = sop_match.group(1) if sop_match else ""

    # 如果提取失败，使用已加载的 SOP
    if not extracted_sop and sop_content:
        extracted_sop = f"## 自主探索 SOP\n\n{sop_content}"

    # 匹配任务指令部分
    task_match = re.search(
        r"(##?\s*自主探索任务触发.*?)(?=请开始执行|$)",
        full_prompt,
        re.DOTALL | re.IGNORECASE,
    )
    task_content = task_match.group(1) if task_match else ""

    # 合并核心部分
    core_parts = []
    if extracted_sop:
        core_parts.append(extracted_sop.strip())
    if task_content:
        core_parts.append(task_content.strip())

    # 确保返回有效内容
    if core_parts:
        return "\n\n".join(core_parts)

    # 使用已加载的 SOP 作为 fallback
    if sop_content:
        return f"## 自主探索 SOP\n\n{sop_content}"

    # 最终 fallback：返回 prompt 的前 3000 字符
    return full_prompt[:3000] if full_prompt else "继续执行自主探索任务"