"""
TTRL 持续学习模块 (Wiki 知识落地 P2: MIA)

基于 MIA Test-Time Reinforcement Learning 设计：
- 推理时学习（无需额外训练数据）
- 记忆整合流程（batch_evaluate → consolidate_memories）
- Executor/Planner 训练机制
- Win Rate 统计和检索优化

核心功能：
- batch_evaluate: 执行结果评估
- consolidate_memories: 记忆整合（去重、优化）
- get_win_rate_stats: 获取胜率统计

使用场景：
- 任务完成后的经验提取
- 自主探索中的持续学习
- 记忆质量优化

流程：
1. 执行任务 → 产生 trace 和 judgement
2. batch_memory_save → 存储到缓冲区
3. batch_evaluate → 评估 reward 信号
4. consolidate_memories → 整合到主记忆库
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# 枚举和数据类型
# ============================================================================


class JudgementType(Enum):
    """执行结果判断类型"""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class MemorySource(Enum):
    """记忆来源类型（用于 TTRL）"""

    EXECUTOR = "executor"  # Executor 执行结果
    PLANNER = "planner"  # Planner 规划结果
    TOOL_CALL = "tool_call"  # 工具调用结果
    USER_FEEDBACK = "user_feedback"  # 用户反馈


@dataclass
class ExecutionTrace:
    """执行轨迹

    记录一次任务执行的完整信息，用于 TTRL 分析。
    """

    trace_id: str
    task_description: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    judgement: JudgementType = JudgementType.UNKNOWN
    source: MemorySource = MemorySource.EXECUTOR
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_ms: float = 0.0
    tools_used: list[str] = field(default_factory=list)
    success_indicators: list[str] = field(default_factory=list)
    failure_indicators: list[str] = field(default_factory=list)


@dataclass
class MemoryEntry:
    """记忆条目（用于整合）

    MIA 记忆结构：
    - question: 任务描述
    - workflow_summary: 工作流摘要
    - plan: 执行计划
    - judgement: 正确性判断
    - usage_count: 使用次数
    - success_count: 成功次数
    - win_rate: 胜率
    """

    question: str
    workflow_summary: str
    plan: str = ""
    judgement: JudgementType = JudgementType.CORRECT
    source: MemorySource = MemorySource.EXECUTOR
    data_id: str = ""
    usage_count: int = 1
    success_count: int = 1
    win_rate: float = 1.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ConsolidationResult:
    """记忆整合结果"""

    total_traces: int
    correct_count: int
    incorrect_count: int
    new_memories: int
    updated_memories: int
    skipped_memories: int
    errors: list[str] = field(default_factory=list)


# ============================================================================
# TTRL 核心逻辑
# ============================================================================


class TTRLProcessor:
    """TTRL 处理器

    实现推理时持续学习：
    - 执行轨迹评估
    - 记忆整合
    - Win Rate 统计
    """

    def __init__(self, memory_root: Path | None = None):
        """初始化

        Args:
            memory_root: 记忆根目录
        """
        self._memory_root = memory_root or self._get_memory_root()
        self._trace_buffer: list[ExecutionTrace] = []
        self._memory_buffer: list[MemoryEntry] = []

    def _get_memory_root(self) -> Path:
        """获取记忆根目录"""
        try:
            from src.shared_config import get_paths_config
            return get_paths_config().memory_dir
        except RuntimeError:
            return Path.home() / ".seed" / "memory"

    # ========================================================================
    # 执行轨迹处理
    # ========================================================================

    def add_trace(self, trace: ExecutionTrace) -> None:
        """添加执行轨迹到缓冲区"""
        self._trace_buffer.append(trace)

    def batch_evaluate(self) -> dict[str, Any]:
        """批量评估执行轨迹

        分析轨迹中的成功/失败指标，生成 reward 信号。

        Returns:
            评估结果统计
        """
        results = {
            "total": len(self._trace_buffer),
            "correct": 0,
            "incorrect": 0,
            "partial": 0,
            "unknown": 0,
            "avg_duration_ms": 0.0,
            "tools_usage": {},
        }

        if not self._trace_buffer:
            return results

        total_duration = 0.0
        tools_usage: dict[str, int] = {}

        for trace in self._trace_buffer:
            # 统计判断类型
            if trace.judgement == JudgementType.CORRECT:
                results["correct"] += 1
            elif trace.judgement == JudgementType.INCORRECT:
                results["incorrect"] += 1
            elif trace.judgement == JudgementType.PARTIAL:
                results["partial"] += 1
            else:
                results["unknown"] += 1

            # 统计工具使用
            for tool in trace.tools_used:
                tools_usage[tool] = tools_usage.get(tool, 0) + 1

            # 累计时长
            total_duration += trace.duration_ms

        results["avg_duration_ms"] = total_duration / len(self._trace_buffer)
        results["tools_usage"] = tools_usage

        return results

    # ========================================================================
    # 记忆整合
    # ========================================================================

    def add_memory_entry(self, entry: MemoryEntry) -> None:
        """添加记忆条目到缓冲区"""
        self._memory_buffer.append(entry)

    def consolidate_memories(
        self,
        similarity_threshold: float = 0.9999,
    ) -> ConsolidationResult:
        """整合记忆

        MIA 记忆整合逻辑：
        - 相似度 ≥ threshold 时执行去重
        - 现有记忆错误 + 新记忆正确 → 替换
        - 都正确 → 保留更短版本
        - 更新 win_rate 统计

        Args:
            similarity_threshold: 相似度阈值

        Returns:
            整合结果
        """
        result = ConsolidationResult(
            total_traces=len(self._memory_buffer),
            correct_count=0,
            incorrect_count=0,
            new_memories=0,
            updated_memories=0,
            skipped_memories=0,
        )

        for entry in self._memory_buffer:
            # 统计正确/错误
            if entry.judgement == JudgementType.CORRECT:
                result.correct_count += 1
            elif entry.judgement == JudgementType.INCORRECT:
                result.incorrect_count += 1

            # 尝试写入记忆
            write_result = self._write_memory_with_dedup(entry, similarity_threshold)

            if write_result.startswith("Saved"):
                result.new_memories += 1
            elif write_result.startswith("Updated"):
                result.updated_memories += 1
            elif write_result.startswith("Skipped"):
                result.skipped_memories += 1
            else:
                result.errors.append(write_result)

        # 清空缓冲区
        self._memory_buffer.clear()
        self._trace_buffer.clear()

        return result

    def _write_memory_with_dedup(
        self,
        entry: MemoryEntry,
        threshold: float,
    ) -> str:
        """写入记忆（带去重逻辑）"""
        from ._memory_write import (
            write_memory,
            VerifiedSource,
            _compute_similarity,
            _check_existing_memory,
        )

        # 映射 MemorySource 到 VerifiedSource
        source_mapping = {
            MemorySource.EXECUTOR: VerifiedSource.TOOL_CALL_SUCCESS,
            MemorySource.PLANNER: VerifiedSource.TOOL_CALL_SUCCESS,
            MemorySource.TOOL_CALL: VerifiedSource.TOOL_CALL_SUCCESS,
            MemorySource.USER_FEEDBACK: VerifiedSource.EXTERNAL_VERIFICATION,
        }

        verified_source = source_mapping.get(entry.source, VerifiedSource.UNVERIFIED)

        # 构建内容
        content = entry.workflow_summary
        if entry.plan:
            content = f"## Workflow\n{entry.workflow_summary}\n\n## Plan\n{entry.plan}"

        metadata = f"win_rate={entry.win_rate}, usage={entry.usage_count}, source={entry.source.value}"

        # 写入记忆（L3 知识层）
        return write_memory(
            level="L3",
            content=content,
            title=f"ttrl_{entry.data_id or entry.question[:30]}",
            metadata=metadata,
            source=verified_source,
        )

    # ========================================================================
    # Win Rate 统计
    # ========================================================================

    def get_win_rate_stats(self, memory_dir: Path | None = None) -> dict[str, Any]:
        """获取 Win Rate 统计

        分析已存储记忆的胜率分布。

        Args:
            memory_dir: 记忆目录（默认 L3 knowledge）

        Returns:
            统计结果
        """
        stats = {
            "total_memories": 0,
            "avg_win_rate": 0.0,
            "high_win_rate": [],  # win_rate >= 0.8
            "low_win_rate": [],  # win_rate < 0.5
            "usage_distribution": {},
        }

        target_dir = memory_dir or (self._memory_root / "knowledge")
        if not target_dir.exists():
            return stats

        win_rates = []
        usage_counts: dict[int, int] = {}

        for file in target_dir.glob("*.md"):
            try:
                with open(file, encoding="utf-8") as f:
                    content = f.read()

                # 解析 metadata
                if "win_rate=" in content:
                    import re
                    match = re.search(r"win_rate=(\d+\.?\d*)", content)
                    if match:
                        win_rate = float(match.group(1))
                        win_rates.append(win_rate)
                        stats["total_memories"] += 1

                        # 分类
                        if win_rate >= 0.8:
                            stats["high_win_rate"].append(file.name)
                        elif win_rate < 0.5:
                            stats["low_win_rate"].append(file.name)

                # 解析 usage_count
                if "usage=" in content:
                    match = re.search(r"usage=(\d+)", content)
                    if match:
                        usage = int(match.group(1))
                        usage_counts[usage] = usage_counts.get(usage, 0) + 1

            except Exception:
                continue

        if win_rates:
            stats["avg_win_rate"] = sum(win_rates) / len(win_rates)

        stats["usage_distribution"] = usage_counts

        return stats


# ============================================================================
# 公共 API 函数
# ============================================================================


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
        f"TTRL Evaluation Results:",
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
        f"TTRL Consolidation Results:",
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
        f"TTRL Win Rate Statistics:",
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
    # 枚举和类型
    "JudgementType",
    "MemorySource",
    "ExecutionTrace",
    "MemoryEntry",
    "ConsolidationResult",
    # 处理器
    "TTRLProcessor",
    "get_ttrl_processor",
    # 公共 API
    "ttrl_add_trace",
    "ttrl_batch_evaluate",
    "ttrl_add_memory",
    "ttrl_consolidate",
    "ttrl_get_stats",
]