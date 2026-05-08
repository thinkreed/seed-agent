"""TTRL 公共 API 函数 - Test-Time Reinforcement Learning"""

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
    """添加执行轨迹"""
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
    """批量评估执行轨迹"""
    processor = get_ttrl_processor()
    results = processor.batch_evaluate()

    lines = [
        "TTRL Evaluation Results:",
        f"- Total: {results['total']}, Correct: {results['correct']}, "
        f"Incorrect: {results['incorrect']}, Partial: {results['partial']}",
        f"- Avg duration: {results['avg_duration_ms']:.1f}ms",
    ]

    if results["tools_usage"]:
        tools = ", ".join(f"{t}:{c}" for t, c in sorted(results["tools_usage"].items(), key=lambda x: -x[1]))
        lines.append(f"- Tools: {tools}")

    return "\n".join(lines)


def ttrl_add_memory(
    question: str,
    workflow_summary: str,
    judgement: str,
    plan: str = "",
    data_id: str = "",
    source: str = "executor",
) -> str:
    """添加记忆条目"""
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
    """整合记忆"""
    processor = get_ttrl_processor()
    result = processor.consolidate_memories(threshold)

    lines = [
        "TTRL Consolidation Results:",
        f"- Traces: {result.total_traces}, Correct: {result.correct_count}, Incorrect: {result.incorrect_count}",
        f"- New: {result.new_memories}, Updated: {result.updated_memories}, Skipped: {result.skipped_memories}",
    ]

    if result.errors:
        lines.append(f"- Errors: {len(result.errors)} - {result.errors[0][:40]}...")

    return "\n".join(lines)


def ttrl_get_stats() -> str:
    """获取 Win Rate 统计"""
    processor = get_ttrl_processor()
    stats = processor.get_win_rate_stats()

    lines = [
        "TTRL Win Rate Statistics:",
        f"- Total: {stats['total_memories']}, Avg win rate: {stats['avg_win_rate']:.2f}",
        f"- High (>=0.8): {len(stats['high_win_rate'])}, Low (<0.5): {len(stats['low_win_rate'])}",
    ]

    if stats["usage_distribution"]:
        usage = ", ".join(f"{u}x:{c}" for u, c in sorted(stats["usage_distribution"].items()))
        lines.append(f"- Usage: {usage}")

    return "\n".join(lines)


__all__ = [
    "get_ttrl_processor",
    "ttrl_add_memory",
    "ttrl_add_trace",
    "ttrl_batch_evaluate",
    "ttrl_consolidate",
    "ttrl_get_stats",
]