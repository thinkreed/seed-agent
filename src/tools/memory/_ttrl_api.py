"""TTRL 公共 API 函数

Wiki 知识落地 P2 (MIA): Test-Time Reinforcement Learning
"""

from typing import Any

from ._ttrl_processor import TTRLProcessor
from ._ttrl_types import ExecutionTrace, JudgementType, MemoryEntry, MemorySource

_processor: TTRLProcessor | None = None


def get_ttrl_processor() -> TTRLProcessor:
    """获取 TTRL 处理器单例"""
    if _processor is None:
        _processor = TTRLProcessor()
    return _processor


def ttrl_add_trace(
    trace_id: str,
    task_description: str,
    judgement: str,
    steps: list[dict[str, Any]] | None = None,
    tools_used: list[str] | None = None,
    duration_ms: float = 0.0,
) -> str:
    """添加执行轨迹（同步 API）

    Args:
        trace_id: 轨迹 ID
        task_description: 任务描述
        judgement: 判断结果（correct/incorrect/partial/unknown）
        steps: 执行步骤列表
        tools_used: 使用工具列表
        duration_ms: 执行时长

    Returns:
        添加结果消息
    """
    processor = get_ttrl_processor()

    try:
        judgement_type = JudgementType(judgement.lower())
    except ValueError:
        judgement_type = JudgementType.UNKNOWN

    trace = ExecutionTrace(
        trace_id=trace_id,
        task_description=task_description,
        judgement=judgement_type,
        steps=steps or [],
        tools_used=tools_used or [],
        duration_ms=duration_ms,
    )

    processor.add_trace(trace)
    return f"Trace added: {trace_id} (judgement={judgement})"


def ttrl_batch_evaluate() -> str:
    """批量评估执行轨迹

    Returns:
        评估结果摘要
    """
    processor = get_ttrl_processor()
    results = processor.batch_evaluate()

    lines = [
        "TTRL Evaluation Results:",
        f"- Total traces: {results['total']}",
        f"- Correct: {results['correct']}",
        f"- Incorrect: {results['incorrect']}",
        f"- Partial: {results['partial']}",
        f"- Avg duration: {results['avg_duration_ms']:.1f}ms",
    ]

    if results["tools_usage"]:
        lines.append("- Tools usage:")
        for tool, count in sorted(results["tools_usage"].items(), key=lambda x: -x[1]):
            lines.append(f"  {tool}: {count}")

    return "\n".join(lines)


def ttrl_add_memory(
    question: str,
    workflow_summary: str,
    judgement: str,
    plan: str = "",
    data_id: str = "",
    source: str = "executor",
) -> str:
    """添加记忆条目

    Args:
        question: 任务描述
        workflow_summary: 工作流摘要
        judgement: 判断结果
        plan: 执行计划
        data_id: 数据 ID
        source: 来源类型

    Returns:
        添加结果消息
    """
    processor = get_ttrl_processor()

    try:
        judgement_type = JudgementType(judgement.lower())
    except ValueError:
        judgement_type = JudgementType.UNKNOWN

    try:
        source_type = MemorySource(source.lower())
    except ValueError:
        source_type = MemorySource.EXECUTOR

    entry = MemoryEntry(
        question=question,
        workflow_summary=workflow_summary,
        plan=plan,
        judgement=judgement_type,
        data_id=data_id,
        source=source_type,
    )

    processor.add_memory_entry(entry)
    return f"Memory entry added: {data_id or question[:30]} (judgement={judgement})"


def ttrl_consolidate(threshold: float = 0.9999) -> str:
    """整合记忆

    Args:
        threshold: 相似度阈值

    Returns:
        整合结果摘要
    """
    processor = get_ttrl_processor()
    result = processor.consolidate_memories(threshold)

    lines = [
        "TTRL Consolidation Results:",
        f"- Total traces: {result.total_traces}",
        f"- Correct: {result.correct_count}",
        f"- Incorrect: {result.incorrect_count}",
        f"- New memories: {result.new_memories}",
        f"- Updated memories: {result.updated_memories}",
        f"- Skipped memories: {result.skipped_memories}",
    ]

    if result.errors:
        lines.append(f"- Errors: {len(result.errors)}")
        for error in result.errors[:3]:
            lines.append(f"  {error[:50]}...")

    return "\n".join(lines)


def ttrl_get_stats() -> str:
    """获取 Win Rate 统计

    Returns:
        统计结果摘要
    """
    processor = get_ttrl_processor()
    stats = processor.get_win_rate_stats()

    lines = [
        "TTRL Win Rate Statistics:",
        f"- Total memories: {stats['total_memories']}",
        f"- Avg win rate: {stats['avg_win_rate']:.2f}",
        f"- High win rate (>=0.8): {len(stats['high_win_rate'])}",
        f"- Low win rate (<0.5): {len(stats['low_win_rate'])}",
    ]

    if stats["usage_distribution"]:
        lines.append("- Usage distribution:")
        for usage, count in sorted(stats["usage_distribution"].items()):
            lines.append(f"  {usage} times: {count} memories")

    return "\n".join(lines)


__all__ = [
    "get_ttrl_processor",
    "ttrl_add_memory",
    "ttrl_add_trace",
    "ttrl_batch_evaluate",
    "ttrl_consolidate",
    "ttrl_get_stats",
]